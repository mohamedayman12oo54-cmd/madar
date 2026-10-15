# BILL-WU-023 — Reconciliation of ambiguous / pending / missed outcomes

**ID:** BILL-WU-023 · **Workstream/Package:** BILL-WS-F / BILL-WP-F2
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** BILL-EXT-03 (Kashier status-lookup / order-reconciliation API semantics; commercial-model
lists "Provider-specific ambiguous-outcome recovery procedure" as Open, external verification required).
Timing values (how long before an attempt is reconciled or expired) are operational settings, not
commercial numbers.
**Priority / Risk:** P0 / High (the duplicate-charge guard)

## Purpose
Resolve attempts whose outcome Madar doesn't know: a charge call that timed out (`unknown`), an attempt
stuck `pending`, a checkout whose webhook never arrived. This is the second trusted path ADR-016 permits
("an internal reconciliation job polling Kashier's own status-lookup API"), and it must run **before**
any new charge for the same period (commercial-model §Failed renewal: reconcile before risking a
duplicate charge).

## Expected outcome
`reconcile_billing_attempts` worker command (same atomic-claim template as BILL-WU-022). For attempts in
`unknown`/`pending` older than a configured age, it calls `provider.lookup_order(merchant_order_id)` and
feeds the result through the **same** transition functions as webhook events (BILL-WU-021). It does not
use a second state machine. If the lookup is also inconclusive, the attempt stays unresolved and is
alerted. Abandoned checkout attempts (no provider record) are moved to a terminal "abandoned/expired"
state after a configured age, so a new checkout may start. A renewal attempt that is unresolved
**blocks** creating another charge attempt for that period. The partial unique index from BILL-WU-008
enforces this structurally.

## Requirement / invariant references
ADR-016 (reconciliation as a trusted path); ADR-017 (reconciliation distinct from receipt); commercial-model §Failed renewal (ambiguous outcomes).

## Relevant ADRs / contracts
ADR-012, ADR-016, ADR-017.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-021 | BLOCKING | Yes | Shared transition functions |
| BILL-WU-018 | CONTRACT | Non-blocking for build (fake lookup); blocking for sandbox | Lookup API |
| BILL-EXT-03 | EXTERNAL | Non-blocking for build; blocking for VERIFIED | Lookup semantics |

## Preconditions
None.

## In-scope changes
Command, lookup-result mapping, tests.

## Explicit exclusions
Retry charges (BILL-WU-030); manual refund flows.

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/management/commands/reconcile_billing_attempts.py`; template `process_ai_operations.py`.

## Data-integrity & security considerations
The lookup call runs outside transactions; results are applied under the same lock order. Reconciliation
never creates a charge.

## Failure modes
Lookup API unavailable (attempt stays unresolved and alerted; no new charge); contradiction with a later
webhook (alerted, terminal precedence per BILL-WU-021).

## Acceptance criteria
- **AC-BILL-023-1:** An `unknown` renewal attempt resolved as paid by lookup marks the period paid with no second charge attempted.
- **AC-BILL-023-2:** While an attempt for a period is unresolved, no new charge attempt for that period can be created (constraint plus service check).
- **AC-BILL-023-3:** An inconclusive lookup leaves state unchanged and alerts.
- **AC-BILL-023-4:** An abandoned checkout attempt becomes terminal after the configured age; a new checkout is then allowed.
- **AC-BILL-023-5:** Two concurrent reconcilers handle an attempt once.

## Verification methods & required evidence
Tests with the fake provider's scripted lookups; sandbox lookup via BILL-WU-036.

## Dependencies required before execution
BILL-WU-021.

## Completion definition
AC-1..5 VERIFIED; sandbox lookup evidence via BILL-WU-036.

## Commit boundaries
`feat(billing): add payment attempt reconciliation worker`; `test(billing): cover reconciliation and duplicate-charge guard`.

## Escalation conditions
Kashier provides no usable status lookup. Then ambiguous outcomes can't be resolved automatically, which affects the BILL-WU-026 go/no-go: escalate.
