# BILL-WU-019 — Checkout initiation, correlation, redirect handling

**ID:** BILL-WU-019 · **Workstream/Package:** BILL-WS-E / BILL-WP-E2
**Status:** READY WITH A TRACKED OPEN ITEM
**Open items:** BILL-EXT-05 (Kashier recurring-agreement consent requirements and the consent text shown to
the teacher); BILL-EXT-01 (agreement cadence parameters); BILL-EXT-03 (whether the setup session itself
charges the first period or only tokenizes; this decides whether activation follows the setup webhook or a
subsequent pay-with-token). Plan change while a paid period is active is OUT OF SCOPE (BILL-WU-039).
**Priority / Risk:** P0 / High

## Purpose
Let an authenticated environment owner choose one of the three plans and start Kashier's hosted
recurring-setup flow, with a Madar-generated correlation key, **without** the browser redirect ever
counting as proof of payment (ADR-016).

## Expected outcome
- `POST /api/v1/billing/checkout/` (mounted under BILL-WU-031's namespace). Permissions:
  `[IsTeacher, IsEnvironmentMember.for_role("owner")]`. Allowed in **every** access state (billing
  resolution is always permitted). The body carries only a plan identifier; price comes from the Plan row.
- In one transaction: lock the Subscription row; refuse if a paid period is currently active on any plan
  (no plan change, OUT OF SCOPE) or if a non-terminal checkout attempt already exists (return it instead,
  for idempotency against double-click); create a `PaymentAttempt` (initiated) with a fresh unguessable
  merchant order id, plan, expected amount and currency.
- Outside the transaction: call `create_recurring_setup_session`. On success store `provider_session_ref`
  and return `{session_url, attempt_id}`. On provider failure, mark the attempt failed-to-initiate and return
  a stable error.
- `GET /api/v1/billing/checkout/return/` (or a Frontend route; decided in BILL-WU-032) is **display only**.
  It returns the attempt's current server-side status (likely `pending`) and **never** changes state, even
  if query parameters say "success". Kashier's redirect signature may optionally be verified for UX
  messaging, but it carries no trust weight.

## Requirement / invariant references
ADR-016 trust-boundary distinctions; AL-3; AL-4 (checkout initiation, pending states); commercial-model §Plans, §Auto-renewal.

## Relevant ADRs / contracts
ADR-015, ADR-016, ADR-017 (payment-attempt tracking), ADR-008/010.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-008 | BLOCKING | Yes | PaymentAttempt |
| BILL-WU-009 | DATA | Yes | Plan price |
| BILL-WU-017 | CONTRACT | Yes | Provider interface (fake suffices for tests) |
| BILL-WU-031 | CONTRACT | Yes | URL namespace |
| BILL-WU-018 | CONTRACT | Non-blocking for build/test; blocking for sandbox verification | Real Kashier |
| BILL-EXT-05 | EXTERNAL | Non-blocking for build; blocking for live | Consent |

## Preconditions
Fake provider available.

## In-scope changes
Checkout service, view, serializer (plan id only), return/status view, tests.

## Explicit exclusions
Activating the subscription here (only BILL-WU-021 may do that); upgrades/downgrades; discount codes; storing card data.

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/{views.py,serializers.py,services.py,urls.py}`; permission pattern `ai/views.py:14`; error envelope `config/exceptions.py`.

## Data-integrity & security considerations
Mass assignment: the serializer exposes no amount, currency, status or environment fields (pattern:
`financials/serializers.py`, and the existing `test_unexpected_fields_cannot_overwrite_server_controlled_state`
at `config/test_security_audit.py:228`). Tenant is server-derived. A merchant order id must not be
guessable, and it must not encode the environment id in a forgeable way.

## Failure modes
Provider unavailable (attempt marked failed-to-initiate, retry allowed); double-click (returns the existing
non-terminal attempt); teacher abandons checkout (attempt stays pending, then reconciliation or expiry per
BILL-WU-023).

## Acceptance criteria
- **AC-BILL-019-1:** A teacher owner can start checkout for each plan; the response contains a session URL; a PaymentAttempt exists with the plan's server-side price.
- **AC-BILL-019-2:** Sending `amount`, `currency`, `status` or `environment_id` in the body has no effect.
- **AC-BILL-019-3:** Calling the return endpoint with any query parameters does not change Subscription, PaymentAttempt or entitlement state.
- **AC-BILL-019-4:** A second checkout request while one is non-terminal returns the same attempt (no second attempt).
- **AC-BILL-019-5:** Non-owners, students, and teacher B with A's header are refused (owner role and tenant checks).
- **AC-BILL-019-6:** Checkout is permitted for an environment whose trial has expired.
- **AC-BILL-019-7:** No provider call happens inside a DB transaction.

## Verification methods & required evidence
Integration tests (fake provider); sandbox flow via BILL-WU-036.

## Dependencies required before execution
BILL-WU-008, 009, 017, 031.

## Completion definition
AC-1..7 VERIFIED with fake; sandbox evidence attached via BILL-WU-036.

## Commit boundaries
`feat(billing): add plan checkout initiation`; `test(billing): cover checkout correlation and redirect non-trust`.

## Escalation conditions
Any request to activate on redirect; plan-change requirements; Kashier consent requirements needing Backend-stored consent records (new data, so record a decision).
