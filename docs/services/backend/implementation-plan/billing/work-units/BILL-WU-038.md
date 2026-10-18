# BILL-WU-038 — Refunds

**ID:** BILL-WU-038 · **Workstream/Package:** BILL-WS-K / BILL-WP-K1
**Status:** OUT OF SCOPE
**Reason:** commercial-model §Open items: "Refund eligibility and process — Open"; §Cancellation: cancellation "does **not** itself imply a refund."
**Priority / Risk:** — / Medium (Kashier's go-live smoke recommends a refund; Madar handles it manually through the Kashier dashboard, BILL-WU-037)

## Purpose
Tracked placeholder so refund capability isn't silently assumed or partially built.

## Expected outcome
None in this plan. Refund-type webhook events are **stored and not applied** (BILL-WU-021 AC-8).

## Requirement / invariant references
commercial-model §Open items.

## Relevant ADRs / contracts
ADR-017 (event separation).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| Refund policy decision (product) | DECISION | Yes, for any future in-scope version | Policy open |

## Preconditions
Not applicable.

## In-scope changes
None.

## Explicit exclusions
Any refund API call, refund endpoint, or automatic refund on cancellation.

## Implementation surfaces (grounded at bf115df)
None. A future version would touch `billing/providers/kashier.py` and `billing/events.py`.

## Data-integrity & security considerations
Refund events received must not alter entitlement automatically.

## Failure modes
A refund issued manually in the Kashier dashboard leaves Madar showing "paid". Operations must
reconcile manually; this is recorded in BILL-RISK-30.

## Acceptance criteria
- **AC-BILL-038-1:** No refund-initiating code exists in `billing/` (review), and refund events are not applied (covered by AC-BILL-021-8).

## Verification methods & required evidence
Review.

## Dependencies required before execution
Not planned.

## Completion definition
Remains OUT OF SCOPE until a policy decision re-scopes it.

## Commit boundaries
None.

## Escalation conditions
Any request to build refunds before a policy exists.
