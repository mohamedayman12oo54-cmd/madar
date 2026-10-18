# BILL-WU-022 — Event-processing recovery worker (`process_billing_events`)

**ID:** BILL-WU-022 · **Workstream/Package:** BILL-WS-F / BILL-WP-F2
**Status:** READY
**Priority / Risk:** P0 / High

## Purpose
Guarantee that every durably received, verified event is eventually applied after interruptions
(crash, deploy, DB blip during in-request application). This is the "recovery after interruption"
leg of ADR-017.

## Expected outcome
A management command `process_billing_events`, modeled on
`apps/backend/ai/management/commands/process_ai_operations.py`: `--limit`, `--loop`, `--interval`,
`--max-iterations`, `--requeue-stale-minutes`. It selects events in `received` (and stale `processing`),
**claims atomically** with a single conditional UPDATE (`:35-43` pattern), and calls
`billing.events.apply` (BILL-WU-021). It increments an attempts counter and records last error. After N
failed attempts it marks the event `needs-attention` and alerts. N is an **operational** setting with a
documented default for this job's own safety. It is not a commercial retry policy. **Does not copy
`process_notifications.py`**, which has no claim step.

## Requirement / invariant references
ADR-017 (recovery); ADR-012 (Worker role, no broker); OP-PARITY; EX-1 (context from server state: the event record).

## Relevant ADRs / contracts
ADR-012, ADR-017.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-021 | BLOCKING | Yes | Application logic |
| BILL-OPS-01 (production scheduler) | OPERATIONAL | Non-blocking for build/verify; blocking for production reliance | Scheduling is delivered by BILL-WU-027, which depends on **this** unit (edge 022 → 027), not the reverse |

## Preconditions
None.

## In-scope changes
Command plus tests (two concurrent claimers; stale requeue; poison event).

## Explicit exclusions
New broker; renewal and reconciliation logic (BILL-WU-023/025).

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/management/commands/process_billing_events.py`; template `apps/backend/ai/management/commands/process_ai_operations.py:35-125`.

## Data-integrity & security considerations
Claim atomicity prevents double application across workers; application itself is idempotent (BILL-WU-021), giving defense in depth.

## Failure modes
Poison event loops forever (bounded attempts, then needs-attention); worker crash leaves `processing` (stale requeue).

## Acceptance criteria
- **AC-BILL-022-1:** An event left `received` (simulated in-request failure) is applied by one run.
- **AC-BILL-022-2:** Two concurrent runs apply an event exactly once.
- **AC-BILL-022-3:** A stale `processing` event is requeued and applied.
- **AC-BILL-022-4:** A consistently failing event ends `needs-attention` after the configured attempts, without blocking others.

## Verification methods & required evidence
Command tests with `--max-iterations 1`; concurrency test (`TransactionTestCase`).

## Dependencies required before execution
BILL-WU-021.

## Completion definition
AC-1..4 VERIFIED.

## Commit boundaries
`feat(billing): add billing event recovery worker`; `test(billing): cover event worker claim and recovery`.

## Escalation conditions
Any proposal to add a broker or to reuse the notification worker pattern.
