# Security audit — what was actually tested

Not a checklist of claims: `backend/config/test_security_audit.py` contains 28
**adversarial** tests that attack the running API. They are part of
`manage.py test` and fail the build if a control regresses.

## What the attacks cover

| Attack | Result |
|---|---|
| Teacher B points the active-environment header at Teacher A's environment (8 endpoints) | 403 on all |
| Teacher B uses their OWN valid header but Teacher A's object ids (5 endpoints) | 404, no data leak |
| Cross-tenant WRITES (attendance, recitation, payments, enrolment rename) | refused; rows verified unchanged |
| Private notes read across teachers | not returned |
| Another teacher's scanned badge | 404 (identical to an unknown token — no existence oracle) |
| Student calling teacher endpoints (6) | 401/403 |
| Student or teacher curating the Knowledge Base | 403 (maintainer-only) |
| Anonymous access (8 endpoints) | 401 |
| Student passing another student's `enrollment_id` | ignored; own data only |
| SQLi / XSS / path traversal / template / command injection / null byte in search | harmless; table intact |
| Oversized prompt (50k chars) | 400, not a crash |
| Wrong types (string/list/null where int expected) | 400 |
| Mass-assignment (`environment_id`, `id`, `qr_token`, `is_active`) | server-controlled fields ignored |
| AI history across users | 404, no content leak |
| Prompt injection trying to bind an assistant op to a student | structurally impossible (DB CheckConstraint) |
| Password hash / secret leakage in responses | none |
| Stack traces / SQL / filesystem paths in errors | none |
| Login error for unknown vs wrong password | byte-identical (no account enumeration) |
| Tampered / garbage / empty / Basic auth tokens | 401 |
| Environment id the caller is not a member of, and bogus ids | 403/400 |

## Fixed during this audit

* **Scanner endpoints had no rate limit.** Added `ScanRateThrottle`
  (`scan: 240/min`, per user) to all five scan endpoints, with tests proving
  badge-grinding is cut off at the cap while a 40-student classroom pace is
  not throttled.

## Verified configuration

* `check --deploy` with DEBUG off: **no issues**.
* Settings refuse to boot in production with non-HTTPS CORS origins, a
  wildcard/empty `ALLOWED_HOSTS`, or a weak secret — verified by triggering it.
* `SECURE_CONTENT_TYPE_NOSNIFF`, `X_FRAME_OPTIONS=DENY`, referrer policy,
  HSTS, secure+HttpOnly cookies, `CORS_ALLOW_CREDENTIALS=False`, no wildcard
  origin.
* MD5 password hasher is guarded behind `if "test" in sys.argv` — asserted by
  a test so it can never reach production.
* No raw SQL anywhere; all queries go through the ORM.

## Dependency advisories — assessed, not ignored

`npm audit` reports open-redirect / XSS-via-open-redirect advisories in
react-router 6. Upgrading to v7 was attempted and **reverted**: v7's packaging
breaks the SSR test harness, and shipping a green build with a broken test
suite is worse than a non-exploitable advisory.

The advisories require navigation to a **user-controlled path**. Every
navigation target in this app was enumerated: all are developer-supplied
literals or constants (`/app`, `/auth/...`, a static CTA map, a `LOGIN_PATH`
lookup, a `back` prop passed as a fixed string). **No navigation target derives
from user input, URL parameters, or an API response**, so the advisories are
not reachable here. Re-assess when upgrading React Router.

## Video system (uploaded files) — 38 tests

Real file upload replaced link-pasting. Security properties under test:

* **Private storage.** `MEDIA_ROOT` is not web-served and `MEDIA_URL` is unset;
  there is no public URL for any video. Verified that neither the teacher nor
  the student API ever serialises the stored path.
* **Upload validation beats the client.** Extension whitelist + declared
  content-type + the file's own **magic bytes**. Rejected in tests: `.php`,
  `.exe`, `.sh`, ELF, ZIP, a text file renamed `.mp4`, a double extension
  `lesson.mp4.php`, empty files, oversized files.
* **The client filename never touches the filesystem.** Storage names are
  random (`videos/<env>/<random>.mp4`), so `../../../../etc/passwd.mp4`
  uploads harmlessly and lands inside the env folder — asserted.
* **Signed, short-lived playback.** Streaming requires a `TimestampSigner`
  ticket bound to the item AND the viewer id, expiring in minutes. Rejected in
  tests: forged, tampered, truncated, upper-cased, hand-written and expired
  tickets, plus a valid ticket presented by a *different* viewer.
* **Authorisation is re-checked at stream time**, so unpublishing, deleting the
  upload, or deactivating the enrolment kills an unexpired ticket immediately.
* **Audience enforcement**: an untargeted student and another teacher both get
  404; anonymous gets 401.
* **Replacement deletes the old blob** (asserted on disk), so superseded files
  cannot linger or be streamed.
* Responses are `nosniff`, `inline`, `private, no-store`; Range requests are
  supported for seeking; `X-Accel-Redirect` is available so nginx can serve the
  bytes instead of Django.
* Uploads are throttled (`video-upload: 20/hour` per teacher).

**Progress tracking** carries no enrollment id — it is derived from the token,
so a student cannot write progress onto someone else's record (asserted), and
progress never moves backwards.

## Video pipeline — what is built vs. what needs infrastructure

Built and tested here (12 resumable-upload tests + 38 video tests):

* **Resumable upload.** Server-held offset; `POST` creates a session, `GET`/`HEAD`
  reports the offset, `PATCH` continues, `DELETE` abandons. A dropped
  connection resumes and the reassembled file is asserted byte-identical.
  The client re-syncs from the server on a 409 rather than trusting its own
  position, and retries with backoff on a network drop.
* **Limits enforced before bytes are written** (declared size, extension,
  content type, max concurrent sessions per teacher) and again as they arrive
  (the total can never exceed what was declared).
* **Chunking is not a validation bypass**: magic-byte validation runs on the
  assembled file, so a PHP payload sent in two chunks is still rejected and the
  partial file deleted.
* **Processing state machine** on the item (uploading → processing → ready /
  failed) with a `trace_id` tying upload → processing → playback → logs.
* **Provider seam** (`content/providers.py`): the interface is shaped for a
  hosted provider — `direct_upload()` returns an endpoint the CLIENT sends to,
  so bytes need not pass through Django twice. `LocalStorageProvider` is the
  implemented default.

Needs infrastructure that does not exist in this project, and is therefore NOT
faked: transcoding to multiple bitrates, HLS/DASH packaging and adaptive
bitrate, CDN delivery, provider webhooks, DRM, and storage lifecycle tiering.
A capability that requires an account raises `ProviderUnavailable` instead of
pretending to work.

## Password recovery / OTP — 22 tests

Audited against the full recovery checklist. Already correct and now pinned by
tests: hashed codes (never plaintext), 5-attempt cap claimed by a single
conditional UPDATE (so concurrent guesses cannot each get a free try), expiry
checked in code rather than trusted to storage TTL, purpose pinning, single-use
consumption via conditional delete (no replay), generic responses that do not
enumerate accounts, separate throttles on request and verify, and full session
revocation on reset (session_version bump + refresh-token blacklist).

Two real gaps found and fixed:

* **Codes came from `random.randint`** — a Mersenne Twister, reconstructible
  from observed output, so an attacker collecting a few codes could predict the
  next. Now `secrets.randbelow(1_000_000)`: OS CSPRNG, uniform, no modulo bias,
  formatted and compared as a STRING so a leading zero survives.
* **Requesting a new code left the old one live.** Each request created a fresh
  pending row, so pressing "send again" produced two simultaneously valid
  codes and a leaked older one still worked. `supersede_pending()` now
  invalidates the previous unverified flow for the same target AND purpose
  (scoped, so a reset never cancels an unrelated claim; and a flow whose code
  is already verified is not wiped mid-way).

Both fixes were verified by reintroducing the fault and watching the tests fail.

## Changed guarantee — teacher notes are now student-visible

Previously the documentation and this audit stated that teacher notes are
teacher-only and never reach the student. **The product owner changed that
decision**, so notes now appear inside the student's own evaluation.

What changed: `studentarea` EvaluationView returns the notes for THIS
enrolment, and the teacher-facing UI was relabelled from "ملاحظات خاصة" ("…لا
يراها الطالب أبدًا") to "ملاحظات المعلّم" with "يراها الطالب ضمن تقييمه", so a
teacher is never writing candidly under a promise that no longer holds.

What did NOT change, and is still asserted by tests: notes are scoped to one
enrolment (a student never sees a peer's), they appear only in the evaluation
section, draft ratings are still withheld, and the guardian portal still does
not include them.

The System/Backend documentation must be updated to match; until then the code
and the docs disagree on this point.

## Broadcast targeting — real bug found and fixed

Selecting a grade AND a group sent the message to everyone in the grade **OR**
the group (`Q(grade) | Q(group)`), so a message aimed at one group reached the
whole year. Targeting is now a narrowing filter: grade+group = that group,
grade alone = the grade, group alone = that group. Verified by reintroducing
the `|` and watching the tests fail.

A broadcast is now also recorded ONCE (`Broadcast`), with the per-student rows
linked to it: the teacher's log shows one entry per message with its audience
and recipient list, and the student can open the full message. Cross-tenant
reads of another teacher's broadcasts are refused (404), asserted by test.

## CORS preflight broke resumable upload (fixed)

The chunked PATCH carries a custom `Upload-Offset` header, which makes the
browser send a preflight. `upload-offset` was not in `CORS_ALLOW_HEADERS`, so
the browser blocked the request **before it reached Django** — nothing in the
server log, and the user saw only a bare "unexpected error". `upload-offset`,
`upload-length` and `tus-resumable` are now allowed, and the offset headers are
added to `CORS_EXPOSE_HEADERS` so the client can read the server's
authoritative offset in order to resume. Pinned by tests.

## Playback URLs are now bearer credentials (deliberate, documented)

To stream natively (instant start, seeking, speed control) the `<video>` src
must authenticate itself — an element cannot send an Authorization header. The
stream endpoint therefore accepts the signed ticket ALONE.

What this costs: anyone holding a LIVE ticket URL can stream it. What still
protects the content: the ticket is unforgeable (signed), names exactly one
item, carries the viewer it was issued to, **expires in 120 seconds**, and the
server re-checks that viewer's live authorisation (published, targeted, active
enrolment, environment owner) on EVERY request — so revoking access or
unpublishing kills an unexpired ticket immediately.

The previous design re-checked the ticket against the requesting session, which
was stricter, but it forced the player to download the entire file into a blob
before playing anything. That is the trade-off, made explicitly rather than by
accident, and asserted by test.

## Honest scope note

Features that do not exist yet were not audited because there is nothing to
audit: the smart monthly evaluation. The "one group only" rule is not implemented because it contradicts
INV-4 in four places in the approved documentation.

## Guardian login — no account, gated on the child's activation

A guardian signs in with the phone number the teacher recorded
(`Enrollment.parent_phone`) plus an OTP sent to it. They never create or
activate an account: no `User` row is made for them.

* **Gate:** a guardian can follow a child only once the CHILD has activated
  their own account (`student.is_active and student.is_verified`). The same
  filter runs at request time, at the OTP→session exchange, and on **every**
  portal request, so deactivating the student (or correcting the number) ends
  an existing guardian session immediately.
* **No oracle:** a number that is unknown, belongs to a teacher, or belongs to a
  guardian whose child has not activated yet all get the same refusal text, and
  no OTP is created for any of them.
* **OTP endpoints:** `/auth/otp/parent-access/verify|resend/` were missing from
  the flow map, so the guardian code could not actually be verified through the
  API. Added; the flow stays purpose-pinned (a student-claim `pending_id` cannot
  be exchanged for a guardian session — asserted).
* **Several children:** one verified number returns a read-only session per
  child (all share the same proven phone); each session is still bound to a
  single enrolment.

## Activation & signup: choice of OTP channel + student code (new)

**Student activation** now needs two independent proofs, in this order:

1. **Membership — the student code** (the enrolment's badge code the teacher hands out). Checked
   *before anything is sent*, so the endpoint cannot be used to push SMS/email to arbitrary
   numbers or addresses. Unknown code, deactivated enrolment, already-activated account and a
   phone that is not the one on the student's record all return the **same** `not_found`
   response (asserted byte-identical) — no oracle for codes, numbers or accounts.
2. **Control of a contact — OTP over the student's choice of channel**: SMS to the phone on
   record, or an email of the student's choosing (stored on the account, as verified, only at
   activation; uniqueness is re-checked there).

Then the student creates a password. **Activation no longer issues a session**; the student is
sent to the normal login page and signs in with phone + password. The response carries only a
masked `phone_hint` so a student who activated by email knows which number to use.

**Teacher signup** accepts `otp_channel` (`phone` default, or `email`). Switching channel
supersedes the earlier code (both destinations are invalidated), so only the newest is live.

**Delivery** is now real and lives in one place (`accounts/delivery.py`): email through Django's
email backend (SMTP/Gmail via env vars), SMS through `OTP_SMS_BACKEND` (no provider exists yet:
the default only logs in DEBUG and **raises outside DEBUG** instead of pretending). Flows where
the person typed their own destination (signup, activation) report a delivery failure (503) and
discard the flow; reset and guardian flows never reveal whether an account exists, so a failure
there is logged and the person uses "resend". Reset requests for unknown accounts still send
nothing. Resend always uses the channel originally chosen. Throttling also keys on `email`.

Not changed (decision needed): guardians still have **no account** (see parents/auth.py).

## Billing (Kashier payments) — 23 tests

`billing/test_security.py` extends this practice to the billing attack surface
(BILL-WU-034), built on the same `_Fixture(TenantTestCase)` pattern. Part of
`manage.py test`.

| Attack | Result |
|---|---|
| Teacher B points the active-environment header at Teacher A's billing endpoints (subscription, history, cancel, checkout) | 403 (`environment_forbidden`) on all; the cancel attempt never lands |
| Guessing another tenant's, or a large random, checkout attempt id on the return endpoint | `attempt_id`/`status` both `null` — no data, no error |
| Student or anonymous caller reaching any billing endpoint | 401/403 everywhere except the webhook |
| Webhook: unsigned, wrong-key, tampered-after-signing, validly-signed-but-wrong-mode, oversized (>64 KB) | 400, nothing persisted |
| Webhook: identical event replayed | 409, no second row, no double application |
| Webhook: uncorrelated `merchantOrderId` | received (200) but `failed_to_apply` — never guessed |
| Webhook: amount mismatch vs. the attempt's expected amount | received (200) but the attempt stays non-terminal — never silently accepted |
| Return endpoint with `status=SUCCESS`/`paymentStatus=paid` query params | attempt/subscription state unchanged (a redirect is never proof of payment, ADR-016) |
| Mass-assignment: `amount_minor_units`, `currency`, `status`, `environment_id`, `student_cap` in the checkout body | ignored; server-computed values stored |
| Mass-assignment: `cancel_at_period_end=false`, `environment_id`, `reason` in the cancel body | ignored; the real cancellation still applies |
| Subscription/history responses | never contain the card token, agreement id, or provider transaction/order ids |
| Billing error bodies (DEBUG off) and a rejected webhook payload | no stack trace, SQL, filesystem path, or payload echo |
| Teacher or student assistant submit with a client-supplied `kind` field | ignored — always created as `assistant`, never a gated kind |
| Student quiz request with a client-supplied `kind` field, no Subscription at all | refused by the entitlement check itself (`capability_not_in_plan`), not merely a missing field |
| The set of `AllowAny` views under `billing.urls` | exactly one (`KashierWebhookView`) |

Worker-side entitlement re-check parity (a capability lost between an AI
operation's submission and the worker picking it up) is covered by
`ai.tests.WorkerEntitlementRecheckTests` (BILL-WU-011) — not duplicated here.

## Billing / payments (Kashier) — what was tested

`billing/` carries ~290 tests, including `test_security.py` (adversarial), `test_kashier_adapter.py`
(official vendor test vectors), `test_money_safety.py` (end-to-end through the real adapter) and the
`test_scope_guards.py` static guards. Properties under test:

| Control | Test |
|---|---|
| The webhook is the ONLY new unauthenticated route; it is authenticated by an HMAC over the raw body, constant-time compared, using the mode-specific key | `test_webhooks`, `test_kashier_adapter.WebhookVerificationTests` |
| Signing code matches Kashier's own published digests (not just itself) | `OfficialVectorTests` |
| An event whose `signatureKeys` omits amount / status / order / currency / transaction id is rejected (otherwise a replayed signed event could be edited in the unsigned fields) | `test_an_event_that_does_not_sign_the_fields_we_act_on_is_rejected` |
| Tampered, unsigned, other-mode-key, malformed and non-exact-amount events change nothing | `WebhookVerificationTests`, `EndToEndThroughTheRealAdapterTests` |
| Replay / duplicate delivery never double-applies (dedup key + terminal-state checks + unique ids) | `test_money_safety`, `test_events`, `test_webhooks` |
| Money is credited only when the paid amount and currency are PROVEN equal to the attempt's (a success with no amount is refused) | `test_underpaying_is_never_credited`, `test_wrong_currency_is_never_credited` |
| **Starting a checkout never changes the plan or its capabilities/student cap.** (Found and fixed: `start_checkout` used to write `Subscription.plan` before payment, so a past-due Plan 1 teacher could get Plan 3 features by pressing the button.) The plan changes only when a payment for it is verified | `StartingCheckoutNeverGrantsAPlanTests` |
| The recurring-agreement token is stored un-masked for renewals, but never in the stored event payload/logs, and is scrubbed from the event once applied. (Found and fixed: the old flow only had the REDACTED value available.) | `test_the_stored_event_never_keeps_the_token_and_is_scrubbed_after_applying`, `test_redaction` |
| A transport error, timeout or any HTTP error on a charge is `unknown` (reconciled), never `failed` | `OutboundCallTests` |
| No outbound payment call inside a DB transaction; https only; checkout URL host allow-listed | `SafetyRailTests`, `OutboundCallTests` |
| Redirect back from the payment page changes no state; the UI shows success only from server status | `test_checkout`, `src/dashboard/render.smoke.test.mjs` |
| Production refuses to boot with the fake provider, missing keys, or non-HTTPS webhook/return URLs | `test_provider_settings` |
| One Environment per teacher is enforced by the database (INV-9) and a read-only, PII-free check gates the migration | `environments/test_cardinality.py` |
| Tests are hermetic: a developer `.env` can no longer point the suite at a real LLM or payment provider | `config/settings.py` |

Open (needs a human decision, deliberately NOT defaulted): BILL-EXT-01 (Kashier's answer on exact 30-day
cadence — the agreement parameters are configuration and checkout is refused while unset), BILL-DEC-05
(retry/grace numbers: a failed renewal currently keeps access until policy exists), BILL-DEC-02 (restricted
access ruleset), BILL-DEC-06 (teacher notifications), BILL-EXT-05 (consent wording).

## Second pass — abuse limits, exposure and tooling

| Check | Result |
|---|---|
| `bandit -ll` (medium+) over the whole backend | 1 finding (`urlopen` scheme in the payment adapter) — fixed: https is now enforced inside the transport itself |
| `pip-audit -r requirements.txt` | no known vulnerabilities |
| `check --deploy` with a production-like environment | no issues apart from `SECURE_SSL_REDIRECT`, which is only off because the shipped dev `.env` sets it; the production default is on |
| Hard-coded secrets scan (Google/OpenAI/AWS/GitHub/Slack key shapes, private keys) | clean; the only hits are obviously fake test fixtures |
| Payment endpoints had no rate limit | per-user: checkout 10/h, cancel 10/h, status/history 120/min; per-IP on the unauthenticated webhook 600/min (bounds HMAC CPU, generous for provider retries). Tests: `billing/test_throttles.py` |
| Django admin was always mounted at `/admin/` with an un-throttled login | now OFF in production unless `DJANGO_ENABLE_ADMIN=True`; path configurable with `DJANGO_ADMIN_PATH`. Tests: `config.tests.AdminExposureTests` |
| `private-media/` (uploaded lesson videos) was not git-ignored | added to `.gitignore` |
| Committed secret in `.env.example` (an e-mail app password) | removed; MUST be revoked at the provider (see BILLING-CHANGES.md) |

Still outside the code, needs an operator: rotate the leaked e-mail password and the Gemini key that sat in the shipped
`.env`; put the admin (if enabled) behind a VPN/IP allow-list; IP allow-list the webhook path to Kashier's
addresses at the proxy as an EXTRA layer (never instead of the signature); schedule the three billing workers.
