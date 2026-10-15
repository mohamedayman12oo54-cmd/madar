# BILL-WU-042 — Price-change treatment for existing subscribers

**ID:** BILL-WU-042 · **Workstream/Package:** BILL-WS-K / BILL-WP-K1
**Status:** OUT OF SCOPE
**Reason:** commercial-model §Open items: "Existing-subscriber treatment on future price changes — Open."
**Priority / Risk:** — / Low for V1 (prices are fixed by data migration BILL-WU-009)

## Purpose
Tracked placeholder. BILL-WU-025 copies the price from the Plan row at period creation, and this plan
provides no runtime price-edit path, so the question doesn't arise in V1 unless someone edits Plan rows.

## Expected outcome
None in this plan.

## Requirement / invariant references
commercial-model §Open items.

## Relevant ADRs / contracts
ADR-014.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| Price-change policy (product) | DECISION | Yes, for any future version | Open |

## Preconditions
Not applicable.

## In-scope changes
None.

## Explicit exclusions
Price versioning, grandfathering, subscriber notifications about price changes.

## Implementation surfaces (grounded at bf115df)
None.

## Data-integrity & security considerations
Plan rows are read-only via API (BILL-WU-009/031). An admin edit would change future renewal amounts
silently, which is why BILL-WU-008 registers admin as read-only.

## Failure modes
A manual DB edit to a price changes the next renewals.

## Acceptance criteria
- **AC-BILL-042-1:** No API or admin path can modify Plan prices (covered by BILL-WU-009/031 tests and read-only admin).

## Verification methods & required evidence
Review plus tests.

## Dependencies required before execution
Not planned.

## Completion definition
Remains OUT OF SCOPE until re-scoped.

## Commit boundaries
None.

## Escalation conditions
Any planned price change.
