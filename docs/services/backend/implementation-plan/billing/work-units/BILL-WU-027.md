# BILL-WU-027 — Production scheduler arrangement for billing worker commands

**ID:** BILL-WU-027 · **Workstream/Package:** BILL-WS-G / BILL-WP-G2
**Status:** BLOCKED
**Blocked by:** OPERATIONAL BILL-OPS-01. No scheduler exists for **any** job today. `infra/`, `scripts/`
and `.github/` contain only `.gitkeep` (rechecked 2026-10-15). Both operations docs name no scheduler, and
`operations.md` routes "concrete production scheduling and monitoring for any Billing renewal/reconciliation
job" to Operations.
**Priority / Risk:** P0 for launch / High

## Purpose
Get `process_billing_events`, `reconcile_billing_attempts` and `process_billing_renewals` run reliably in
staging and production, in the Worker role (ADR-012), with liveness monitoring.

## Expected outcome
An Operations-owned, documented arrangement (cron, systemd timer, managed scheduler, or long-running
`--loop` processes under a supervisor; the choice is Operations'). It includes concurrency expectations
(the commands are claim-safe for N > 1), restart policy, and an alert when a command hasn't completed a
run within a threshold.

## Requirement / invariant references
`09-operations/deployment.md`; backend `operations.md` §Routed follow-ups; ADR-012; commercial-model §Open items (scheduling/monitoring).

## Relevant ADRs / contracts
ADR-012.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-OPS-01 | OPERATIONAL | Yes | Owner decision |
| BILL-WU-022, BILL-WU-023, BILL-WU-025 | BLOCKING | Yes (to have something to schedule) | Commands |

## Preconditions
Operations decision recorded.

## In-scope changes
Deployment configuration (location decided by Operations; possibly `infra/`), runbook.

## Explicit exclusions
Choosing a vendor inside this plan; new broker.

## Implementation surfaces (grounded at bf115df)
`infra/` (empty today); the three commands.

## Data-integrity & security considerations
Worker processes need the same secrets and settings as Web (guarantee parity), minus anything Web-only.

## Failure modes
Scheduler silently stops (the liveness alert catches it); overlapping runs (safe by claims).

## Acceptance criteria
- **AC-BILL-027-1:** In staging, all three commands run on schedule for 72 h with run logs.
- **AC-BILL-027-2:** Killing a worker mid-run is recovered on the next run (stale handling observed).
- **AC-BILL-027-3:** A liveness alert fires when a command is stopped beyond the threshold.

## Verification methods & required evidence
Ops records and logs.

## Dependencies required before execution
BILL-OPS-01; BILL-WU-022/023/025.

## Completion definition
AC-1..3 in staging, then production.

## Commit boundaries
If config is kept in-repo: `build(infra): schedule billing worker commands`.

## Escalation conditions
No owner for Operations decisions.
