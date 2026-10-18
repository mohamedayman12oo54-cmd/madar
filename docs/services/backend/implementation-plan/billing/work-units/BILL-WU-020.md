# BILL-WU-020 — Kashier webhook endpoint: signature verification, raw body, durable receipt, dedup

**ID:** BILL-WU-020 · **Workstream/Package:** BILL-WS-F / BILL-WP-F1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** BILL-EXT-03 (confirm in sandbox which key signs webhooks per mode, the exact
`signatureKeys` canonicalisation, and identifiers suitable for dedup).
**Priority / Risk:** P0 / Critical (the system's only inbound external integration)

## Purpose
Implement the **one** ADR-016-approved inbound integration, and nothing broader. It receives Kashier
payment-result callbacks, verifies them cryptographically **before** trusting any byte, records them
durably exactly once, and acknowledges within Kashier's window. Applying state is a separate step
(BILL-WU-021), so ingress stays fast and retry-safe.

## Expected outcome
`POST /api/v1/billing/webhooks/kashier/`:
1. **Authentication model:** DRF `authentication_classes = []` and `permission_classes = [AllowAny]`.
   JWT doesn't apply, because Kashier is not a Madar user. **The HMAC signature is the authentication.**
   CSRF-exempt (DRF APIView without SessionAuthentication). It is the only `AllowAny` endpoint in
   `billing` apart from none.
2. **Raw body:** read `request.body` **before** any parsing and verify against it. Parsed JSON is used only
   after verification. Body size cap (reuse `DATA_UPLOAD_MAX_MEMORY_SIZE` semantics, or a smaller explicit cap).
3. **Verification:** `provider.verify_and_parse_webhook(raw, headers)` using the **mode-specific** key for
   the configured `KASHIER_MODE`. If the payload's mode or merchant doesn't match configuration, reject. On
   failure: respond with a non-2xx code (e.g., 400/401), persist **nothing** except a rate-limited security
   log line with no body (BILL-WU-035), and never touch billing state. ADR-016 prerequisite 1: "an
   unverified request is never processed."
4. **Durable receipt with dedup:** in one short transaction, insert a provider event record (BILL-WU-008)
   with a **dedup key**. Proposed composition, to be confirmed under BILL-EXT-03:
   `sha256(mode | data.transactionId | data.status | event)`, falling back to
   `kashierOrderId`/`merchantOrderId` if `transactionId` is absent. Kashier itself dedups on
   `{transactionId}::{webhookUrl}::{status}` but warns that repeats can still occur. On unique-constraint
   conflict, the event is a duplicate. Return **409** (Kashier treats 409 as "already processed",
   acknowledged), or 200 per BILL-EXT-03 confirmation, and do nothing else. `event="idempotency"` replays
   are handled the same way.
5. **Acknowledge fast:** respond **200** after the receipt commits; don't wait for state application.
   Kashier's timeout is 30 s, and a slower or non-2xx/409 response triggers retries (up to 10, with
   backoff of 2 min, 10 min, 30 min, 1 h, 2 h, 4 h, then every 4 h). Application happens either in-request
   after the commit (best effort, and failure must not change the response) or via the recovery worker
   (BILL-WU-022). Preferred: attempt in-request **after** the receipt commit, with the worker as the
   guarantee.
6. **No Environment from the payload:** the tenant is derived only later, from the correlated internal
   PaymentAttempt (BILL-WU-021). Payload fields such as `merchantDetails` are never used for scoping.

## Requirement / invariant references
ADR-016 (prerequisites 1-3; "only channel permitted to transition billing state"); ADR-017 (provider-event dedup ≠ client-request idempotency); AL-3; external-interfaces §Negative space; BD-27/28.

**The AI `idempotency_key` mechanism (`ai/models.py:65,82-86`, scoped to `(environment, requested_by, key)`)
is NOT reused.** A webhook has no requesting user or environment at receipt time. The provider-event
record's dedup key is a separate mechanism (ADR-017 §Alternatives).

## Relevant ADRs / contracts
ADR-015 concern 4, ADR-016, ADR-017; `07-contracts/api-contract.md` (scoped exception).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-008 | BLOCKING | Yes | Provider event record with unique dedup key |
| BILL-WU-017 | CONTRACT | Yes | `verify_and_parse_webhook` |
| BILL-WU-018 | CONTRACT | Non-blocking for build (fake signs fixtures); blocking for sandbox | Real scheme |
| BILL-EXT-03 | EXTERNAL | Non-blocking for build; blocking for VERIFIED | Confirm key and fields |
| BILL-OPS-04 (public HTTPS URL per env/mode; Kashier rejects localhost/private addresses) | OPERATIONAL | Blocking for sandbox/staging | Reachability |

## Preconditions
ADR-016 re-read; confirm no other inbound route is being added in the same change.

## In-scope changes
View, URL, receipt service, tests (unit plus integration with signed fixtures).

## Explicit exclusions
Any other provider's webhook (including `content/providers.py` video webhooks); state transitions (BILL-WU-021);
treating `merchantRedirectURL` or redirects as signals; IP allow-listing as a **substitute** for signatures
(it may be an extra layer only).

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/webhooks.py` (view), `apps/backend/billing/urls.py`; `apps/backend/config/urls.py:23-38` (namespace via BILL-WU-031); `apps/backend/config/settings.py:278-291` (default auth and permission, overridden per-view only here).

## Data-integrity & security considerations
Constant-time compare; verification precedes any JSON parse that drives logic; the dedup key is unique at
the DB level; replay of an old valid event is idempotent (duplicate). Unknown-but-valid events are stored
with status `ignored` and are not applied. Throttling must not drop legitimate retries; if added, the
limits must be generous and monitored. Don't echo request content in responses.

## Failure modes
DB down at receipt (return 5xx, and Kashier retries; that's correct); a verified event the code doesn't
understand (stored, ignored, alerted); secret rotation (support two keys during rotation, as an Operations
procedure); signature scheme changed by Kashier (all events rejected, so alert; BILL-WU-035).

## Acceptance criteria
- **AC-BILL-020-1:** A correctly signed fixture is stored once and answered 200 within the request.
- **AC-BILL-020-2:** The identical event delivered again yields no new row and a 409 (or the confirmed acknowledged code) with no state change.
- **AC-BILL-020-3:** A wrong signature, missing header, tampered body, or a signature made with the other mode's key is rejected with non-2xx; **no** provider-event row and **no** billing state change.
- **AC-BILL-020-4:** The endpoint ignores JWT (works without an Authorization header) and is not reachable with only a valid JWT and no signature.
- **AC-BILL-020-5:** The test suite proves the AI `idempotency_key` field and constraint are untouched and unused by billing (static check: no reference to `AIOperation` or `idempotency_key` in `billing/`).
- **AC-BILL-020-6:** The URL table gains exactly one new `AllowAny` inbound route; a test enumerates `AllowAny` views and asserts the expected set (guards ADR-016's "no precedent").
- **AC-BILL-020-7:** Receipt commits before any state application; a forced application failure still returns 200 and leaves the event `received`.

## Verification methods & required evidence
Integration tests with fake-signed fixtures; adversarial cases in BILL-WU-034; sandbox delivery in BILL-WU-036.

## Dependencies required before execution
BILL-WU-008, BILL-WU-017.

## Completion definition
AC-1..7 VERIFIED with fixtures; sandbox signature verification evidence via BILL-WU-036.

## Commit boundaries
`feat(billing): add signature-verified Kashier webhook receipt`; `test(billing): cover webhook verification, dedup and replay`.

## Escalation conditions
Any request to accept unsigned callbacks, add another inbound integration, or reuse AI idempotency; Kashier's scheme not matching the docs.
