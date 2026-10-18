# BILL-WU-030 — Retry schedule and grace-period execution

**ID:** BILL-WU-030 · **Workstream/Package:** BILL-WS-H / BILL-WP-H1
**Status:** BLOCKED
**Blocked by:** DECISION BILL-DEC-05 (exact retry count, retry timing, and grace duration are explicitly
Open in commercial-model §Failed renewal and §Open items). Also BILL-DEC-02 for what "access restricted"
means once grace ends.
**Priority / Risk:** P0 for launch / High

## Purpose
After the numbers are decided, schedule limited retry charges for a failed renewal and end access when
grace expires.

## Expected outcome
Shape only: retry attempts created by the renewal worker per the decided schedule, each reusing the
BILL-WU-025 claim and double-charge guards. A retry is only created after the previous attempt is
terminal-failed, never while one is ambiguous. Grace expiry is computed in BILL-WU-010 from the decided
duration.

## Requirement / invariant references
commercial-model §Failed renewal; functional §Billing bullet 4.

## Relevant ADRs / contracts
ADR-017.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-DEC-05 | DECISION | Yes | Numbers |
| BILL-DEC-02 | DECISION | Yes (post-grace behaviour) | Restriction meaning |
| BILL-WU-025, BILL-WU-029 | BLOCKING | Yes | Mechanics and recording |

## Preconditions
Decisions recorded in commercial-model by their owner.

## In-scope changes
Per decision.

## Explicit exclusions
Inventing defaults.

## Implementation surfaces (grounded at bf115df)
`apps/backend/billing/management/commands/process_billing_renewals.py`; `apps/backend/billing/entitlements.py`.

## Data-integrity & security considerations
Same double-charge guarantees as BILL-WU-025; retries never overlap an unresolved attempt.

## Failure modes
Retry storm (bounded by the decided count).

## Acceptance criteria
- **AC-BILL-030-1:** (finalized after BILL-DEC-05) Retries occur exactly per the decided schedule, at most the decided count, never during an unresolved attempt.
- **AC-BILL-030-2:** At grace end without success, entitlement changes to not-granted as decided; no data is deleted.

## Verification methods & required evidence
Frozen-clock tests; sandbox.

## Dependencies required before execution
BILL-DEC-05, BILL-DEC-02, BILL-WU-025, BILL-WU-029.

## Completion definition
AC-1..2 VERIFIED.

## Commit boundaries
`feat(billing): schedule renewal retries and grace expiry per policy`.

## Escalation conditions
Starting without recorded decisions.
