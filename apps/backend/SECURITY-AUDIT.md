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

## Honest scope note

Features that do not exist yet were not audited because there is nothing to
audit: the smart monthly evaluation. The "one group only" rule is not implemented because it contradicts
INV-4 in four places in the approved documentation.
