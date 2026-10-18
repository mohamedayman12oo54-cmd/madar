# BILL-WU-025 — Renewal execution capability (`process_billing_renewals`, atomic claim, single attempt)

**ID:** BILL-WU-025 · **Workstream/Package:** BILL-WS-G / BILL-WP-G1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open items:** BILL-DEC-05 (retry count and schedule, grace duration; this unit makes **one** attempt per
period and never retries automatically); BILL-EXT-01 (production cadence). The command ships **disabled
for live mode** behind a setting (e.g., `BILLING_RENEWALS_LIVE_ENABLED=False`) until BILL-WU-026 passes.
**Priority / Risk:** P0 / Critical (merchant-initiated charging)

## Purpose
Build and verify the renewal mechanics independently of the external 30-day compatibility question.
Madar owns the billing schedule: Kashier has no managed subscriptions, so the merchant charges the saved
token each cycle (Kashier recurring guide, reviewed 2026-10-15). This unit is the **capability**.
BILL-WU-026 is the **gate** for using it in production against the verified Kashier product. The
decomposition is genuine: everything here can be fully verified against the fake provider and in
sandbox. Only "this cadence is acceptable to Kashier's live agreement product" depends on BILL-EXT-01.

## Expected outcome
Command `process_billing_renewals` (template: `process_ai_operations.py`; flags `--limit --loop
--interval --max-iterations --requeue-stale-minutes`). Per run:
1. Select active Subscriptions where `renewal_due` (BILL-WU-024), **not** `cancel_at_period_end`, with a
   stored agreement reference, and no unresolved attempt for the next period.
2. **Claim in one transaction** (lock order: Subscription row first): re-read `cancel_at_period_end` and
   status under the lock; if cancelled or no longer due, skip. Otherwise create the next BillingPeriod
   (BILL-WU-024), its amount-owed record (price **from the Plan row at this moment**; price-change policy is
   OUT OF SCOPE, see BILL-WU-042), and a PaymentAttempt (status `processing`) for that period. The partial
   unique index guarantees one non-terminal attempt per period, which is the structural double-charge guard.
3. **Outside any transaction:** `provider.charge_saved_agreement(attempt, agreement_ref)`.
4. **Persist the outcome** (in a transaction) via the shared transition functions: `succeeded` → period
   paid (access continues seamlessly); `failed` (confirmed) → BILL-WU-029; `pending`/`unknown` → left for
   webhook or BILL-WU-023. **Never** re-charge in the same run.
5. Stale `processing` attempts (worker died after claim, possibly after charging) are **not** retried
   blindly. They move to `unknown` for reconciliation (BILL-WU-023). This deliberately differs from the AI
   worker's requeue-to-pending, because a re-charge could double-bill.
6. Worker context comes only from server-side records (OP-PARITY/EX-1). Entitlement guarantees are
   identical to Web.

## Requirement / invariant references
commercial-model §Billing period, §Auto-renewal, §Cancellation, §Failed renewal (single failure doesn't terminate; reconcile before duplicate charge); ADR-012; ADR-017; OP-PARITY; BD-20.

## Relevant ADRs / contracts
ADR-012, ADR-015, ADR-016 (outbound side), ADR-017.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-024 | BLOCKING | Yes | Due computation |
| BILL-WU-017 | CONTRACT | Yes | `charge_saved_agreement` |
| BILL-WU-021 | CONTRACT | Yes | Shared transition functions |
| BILL-WU-023 | CONTRACT | Yes | Ambiguous outcome path |
| BILL-WU-029 | CONTRACT | Yes | Failure recording |
| BILL-DEC-05 | DECISION | Non-blocking (retries excluded) | Policy |
| BILL-EXT-01 | EXTERNAL | Non-blocking for this unit; blocking for BILL-WU-026 | Production cadence |

## Preconditions
Fake provider can script charge outcomes, including a timeout.

## In-scope changes
Command, service functions, live-mode kill switch, tests.

## Explicit exclusions
Automatic retries or grace expiry (BILL-WU-030); notifications (BILL-WU-033); scheduler setup (BILL-WU-027); price changes; proration.

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/management/commands/process_billing_renewals.py`; `apps/backend/billing/services.py`; template `apps/backend/ai/management/commands/process_ai_operations.py:35-125` (claim, call outside txn, persist inside txn).

## Data-integrity & security considerations
Double-charge prevention has three layers: the claim under lock; the partial unique index (one
non-terminal attempt per period); stale → `unknown`, never → retry. The kill switch is checked at
command start and per charge.

## Failure modes
Crash after charge but before persist (attempt stays `processing`, then stale → `unknown` → reconcile, so
no double charge); cancellation racing the claim (see BILL-WU-028); provider down (`unknown`, then reconcile).

## Acceptance criteria
- **AC-BILL-025-1:** A due subscription with an agreement gets exactly one attempt and one charge call per period; a successful outcome extends access by exactly 30 days.
- **AC-BILL-025-2:** Two concurrent workers produce one attempt and one charge call.
- **AC-BILL-025-3:** A crash simulated after the charge call and before persist leads, on the next run, to `unknown` and **no** second charge call.
- **AC-BILL-025-4:** A confirmed failure is recorded via BILL-WU-029 and no retry is attempted.
- **AC-BILL-025-5:** A subscription with `cancel_at_period_end` is never charged.
- **AC-BILL-025-6:** With `KASHIER_MODE=live` and the live kill switch off, the command charges nothing and logs that it is disabled.
- **AC-BILL-025-7:** No charge call occurs inside a DB transaction.

## Verification methods & required evidence
Command tests with the fake provider; concurrency and crash tests; sandbox renewal via BILL-WU-036.

## Dependencies required before execution
BILL-WU-017, 021, 023, 024, 029.

## Completion definition
AC-1..7 VERIFIED (fake plus sandbox). The unit is complete with production renewals still **disabled**.

## Commit boundaries
`feat(billing): add renewal execution worker with single-attempt claim`; `test(billing): cover renewal claim, crash safety and cancellation skip`.

## Escalation conditions
Any request to auto-retry, to enable live mode before BILL-WU-026, or to requeue stale charges to pending.
