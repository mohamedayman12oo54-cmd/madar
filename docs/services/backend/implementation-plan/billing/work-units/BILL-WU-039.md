# BILL-WU-039 — Upgrade/downgrade timing and proration

**ID:** BILL-WU-039 · **Workstream/Package:** BILL-WS-K / BILL-WP-K1
**Status:** OUT OF SCOPE
**Reason:** commercial-model §Open items: "Upgrade/downgrade timing and proration policy — Open."
**Priority / Risk:** — / Medium (teachers may want to change plan; checkout refuses plan change during an active paid period, BILL-WU-019)

## Purpose
Tracked placeholder for plan changes during a paid period and for over-cap rosters after a downgrade.

## Expected outcome
None in this plan. BILL-WU-019 refuses checkout while a paid period is active; BILL-WU-012 never deactivates students.

## Requirement / invariant references
commercial-model §Open items.

## Relevant ADRs / contracts
ADR-018.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| Upgrade/downgrade and proration policy (product) | DECISION | Yes, for any future version | Policy open |

## Preconditions
Not applicable.

## In-scope changes
None.

## Explicit exclusions
Mid-period plan change; proration math; downgrade roster handling.

## Implementation surfaces (grounded at bf115df)
None.

## Data-integrity & security considerations
Not applicable.

## Failure modes
A teacher wanting a different plan must cancel and wait for period end (a product UX gap; BILL-RISK-31).

## Acceptance criteria
- **AC-BILL-039-1:** Checkout during an active paid period is refused (covered by BILL-WU-019 behaviour); no proration code exists.

## Verification methods & required evidence
Review plus BILL-WU-019 tests.

## Dependencies required before execution
Not planned.

## Completion definition
Remains OUT OF SCOPE until re-scoped.

## Commit boundaries
None.

## Escalation conditions
Requests for plan changes before a policy exists.
