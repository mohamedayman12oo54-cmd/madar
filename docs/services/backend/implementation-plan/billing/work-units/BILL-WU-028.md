# BILL-WU-028 — Cancel-at-period-end with renewal race safety

**ID:** BILL-WU-028 · **Workstream/Package:** BILL-WS-H / BILL-WP-H1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open items:** BILL-EXT-03 (whether Madar should also delete the Kashier token or agreement on
cancellation; `DELETE /v3/payment/tokenization/tokens/:token` exists per docs, but obligations are
unconfirmed); "undo cancellation before period end" is not addressed by commercial-model, so it is excluded
and recorded as an open product question.
**Priority / Risk:** P0 / High (race with charging)

## Purpose
Implement commercial-model §Cancellation: cancellation takes effect at the end of the already-paid period,
stops the **next** renewal only, doesn't cut current access, and doesn't imply a refund. Make it race-safe
against a renewal attempt in flight.

## Expected outcome
`POST /api/v1/billing/subscription/cancel/` (owner only, always permitted). In one transaction, lock the
Subscription row (the **same first lock** the renewal claim takes, BILL-WU-025 step 2) and set
`cancel_at_period_end=True` with `cancel_requested_at`. Idempotent: a repeat call returns the same state.

**Race-safety rule (normative for this plan):** both paths serialize on the Subscription row lock.
- Cancellation commits **before** the renewal claim acquires the lock: the claim re-reads the flag under
  the lock and skips. No attempt and no charge.
- The renewal claim commits **first** (an attempt for the next period now exists, and a charge may be
  in flight outside any transaction): cancellation still sets the flag, but the response states that a
  renewal for the next period was already initiated (stable code, e.g., `renewal_already_in_progress`,
  with the attempt's status). The in-flight charge is **not** cancelled by Madar, since Kashier can't be
  assumed to support aborting it. If it succeeds, the teacher has paid for the next period: access is
  granted through it and cancellation applies at **that** period's end. Whether a refund follows is
  BILL-WU-038 (OUT OF SCOPE / policy open). This outcome is surfaced explicitly, never hidden.
- After the paid period ends with the flag set, entitlement ends (BILL-WU-010). The Subscription moves to a
  cancelled/ended state, and data is retained.

## Requirement / invariant references
commercial-model §Cancellation; functional §Billing bullet 3; AL-4 (cancellation messaging).

## Relevant ADRs / contracts
ADR-017 (subscription state separate from attempts).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-008 | BLOCKING | Yes | Flag field |
| BILL-WU-025 | CONTRACT | Yes | The race partner and its lock order |
| BILL-WU-031 | CONTRACT | Yes | Namespace |
| BILL-EXT-03 | EXTERNAL | Non-blocking | Token deletion obligations |

## Preconditions
Lock order documented (Subscription → PaymentAttempt → event).

## In-scope changes
Service, endpoint, status exposure, race tests.

## Explicit exclusions
Refunds; reactivation/undo; immediate termination; Kashier token deletion (until BILL-EXT-03).

## Implementation surfaces (grounded at bf115df)
`apps/backend/billing/{services.py,views.py,urls.py}`; `process_billing_renewals` claim (BILL-WU-025).

## Data-integrity & security considerations
Mass-assignment safe (no body fields beyond optional reason); tenant and owner checks; no data deletion.

## Failure modes
Deadlock (prevented by single lock order; tested); a cancellation that seems ignored because a charge was in flight (explicit response code).

## Acceptance criteria
- **AC-BILL-028-1:** After cancel, access remains granted until the current period end and ends at period end (frozen-clock test).
- **AC-BILL-028-2:** Cancel committed before the renewal claim results in no attempt and no charge call.
- **AC-BILL-028-3:** Renewal claim committed first, then cancel: the response carries `renewal_already_in_progress`; if the charge succeeds, access extends through that period and ends at its end; no second charge occurs.
- **AC-BILL-028-4:** Concurrent cancel plus renewal claim under `TransactionTestCase` never deadlocks and never yields two attempts.
- **AC-BILL-028-5:** Cancellation creates no refund and deletes no data.
- **AC-BILL-028-6:** Non-owner and cross-tenant cancel attempts are refused.

## Verification methods & required evidence
Integration plus concurrency tests; frozen-clock tests.

## Dependencies required before execution
BILL-WU-008, 025, 031.

## Completion definition
AC-1..6 VERIFIED.

## Commit boundaries
`feat(billing): add cancel-at-period-end`; `test(billing): cover cancellation and renewal race`.

## Escalation conditions
Requirement to abort in-flight charges or to refund on cancel; undo-cancel requirements.
