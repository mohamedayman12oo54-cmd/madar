# BILL-WU-015 — Commercial state for pre-existing teacher accounts (backfill)

**ID:** BILL-WU-015 · **Workstream/Package:** BILL-WS-D / BILL-WP-D1
**Status:** BLOCKED
**Blocked by:** DECISION BILL-DEC-03. What commercial state do teachers who signed up **before** billing
existed receive? Options: a fresh 16-day trial from the deploy instant; a trial from their original
activation (likely already expired); a grandfathered period; something else. Not addressed by commercial-model.
**Priority / Risk:** P0 for launch / High

## Purpose
Make sure every existing teacher Environment has a defined Subscription state at launch. Without one, the
entitlement contract returns `no_subscription` and BILL-WU-011 would deny gated AI to every existing teacher.

## Expected outcome
A data migration or idempotent management command creating Subscriptions for all Environments lacking one,
per the BILL-DEC-03 policy, run after BILL-WU-007 in each DB.

## Requirement / invariant references
commercial-model §Free trial (defines new signups only); INV-9.

## Relevant ADRs / contracts
ADR-014, ADR-018.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-DEC-03 | DECISION | Yes | Policy |
| BILL-WU-014 | BLOCKING | Yes | Reuse `start_trial` or sibling capability |
| BILL-WU-007 | DATA | Yes (per DB) | One Environment per teacher before creating one Subscription per Environment |

## Preconditions
BILL-DEC-03 recorded by product.

## In-scope changes
Backfill command or migration; tests; dry-run output.

## Explicit exclusions
Choosing the policy; notifying teachers (BILL-WU-033).

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/management/commands/backfill_subscriptions.py` (or data migration); `apps/backend/environments/models.py`.

## Data-integrity & security considerations
Idempotent (unique Subscription per Environment makes re-runs safe); dry-run mode; no student data touched.

## Failure modes
A run before BILL-WU-007 on a DB with duplicates (guarded: the command refuses to run if `check_environment_cardinality` fails).

## Acceptance criteria
- **AC-BILL-015-1:** After running, every Environment has exactly one Subscription in the state BILL-DEC-03 specifies.
- **AC-BILL-015-2:** Re-running creates nothing new.
- **AC-BILL-015-3:** The command refuses to run when BILL-WU-003's check fails.

## Verification methods & required evidence
Tests; staging dry-run and real-run logs.

## Dependencies required before execution
BILL-DEC-03, BILL-WU-014, BILL-WU-007 (per DB).

## Completion definition
AC-1..3 VERIFIED; production run logged before launch.

## Commit boundaries
`feat(billing): backfill subscriptions for existing teacher environments`.

## Escalation conditions
Any start before BILL-DEC-03.
