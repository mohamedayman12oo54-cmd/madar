# BILL-WU-021 — Event application: correlation, status semantics, transactional state transitions

**ID:** BILL-WU-021 · **Workstream/Package:** BILL-WS-F / BILL-WP-F2
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** BILL-EXT-03 (whether the recurring-setup webhook carries the token/agreement and whether
setup also captures the first period's payment; which fields identify order vs transaction across
setup and renewal).
**Priority / Risk:** P0 / Critical

## Purpose
Apply a **verified, durably received** provider event to billing state exactly once, keeping ADR-017's
separations: event type vs transaction status vs order status; payment attempt vs amount-owed record vs
subscription vs entitlement.

## Expected outcome
`billing.events.apply(event_record)`, idempotent, called from the webhook (best effort) and from the
recovery worker (BILL-WU-022):
1. **Correlation (ADR-016 prerequisite 2):** find the PaymentAttempt by `merchantOrderId` (Madar-generated,
   BILL-WU-019/025), and cross-check provider order/transaction ids when already known. **No match → mark
   the event `uncorrelated`, don't guess, alert.** The Environment and Subscription come from the
   attempt, never from payload fields.
2. **Consistency checks:** amount and currency equal the attempt's expected values; mode matches. A
   mismatch marks the event `rejected-mismatch`, raises an alert, and changes no state.
3. **Status semantics:** branch on `data.status` (`SUCCESS`/`FAILURE`/`PENDING`), **not** on `event`. Kashier
   uses the same `event` for failures. `event` distinguishes pay vs refund/void/reversal. Refund-type events
   are stored and flagged for manual handling, not applied (BILL-WU-038 is OUT OF SCOPE).
   Order status (paid before, `ORDER_PAID_BEFORE`) is treated as "already succeeded", not a new charge.
4. **Transaction (single DB transaction, lock order: Subscription row → PaymentAttempt row → event row):**
   - `SUCCESS` on a non-terminal attempt: attempt → succeeded; for checkout: store the
     recurring-agreement reference (token plus agreementId, opaque); create the BillingPeriod
     `[t, t+30d)` via BILL-WU-024, where *t* is the Backend's success-processing instant or the provider's
     `creationDate`, decided and recorded; mark the amount-owed record satisfied; Subscription → active on
     the plan. For renewal: the period was pre-created by BILL-WU-025, so mark it paid.
   - `FAILURE`: delegate to BILL-WU-029 (confirmed failure recording).
   - `PENDING`: attempt → pending; no access change.
   - **Out-of-order and terminal precedence:** a terminal attempt is never regressed. A `PENDING` arriving
     after `SUCCESS` is ignored. A `FAILURE` arriving after `SUCCESS` for the **same** transaction is stored,
     not applied, and alerted (possible reversal; manual).
   - Mark the event `processed` in the **same** transaction as the state change, so a crash leaves either
     both or neither (pattern: `process_ai_operations.py:109-120`).
5. **Delayed events:** an event for an attempt already resolved by reconciliation (BILL-WU-023) is a no-op
   when consistent, and alerted when contradictory.

## Requirement / invariant references
ADR-016 (correlation; only trusted channels transition state); ADR-017 (all separations; "a webhook arriving is not proof"); commercial-model §Failed renewal ("ambiguous outcome must be reconciled before risking a duplicate charge"); DAT-5.

## Relevant ADRs / contracts
ADR-015 concern 5, ADR-016, ADR-017, OP-PARITY.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-020 | BLOCKING | Yes | Consumes received events |
| BILL-WU-019 | DATA | Yes | Checkout attempts to correlate to |
| BILL-WU-024 | CONTRACT | Yes | Period creation |
| BILL-WU-029 | CONTRACT | Yes | Failure recording |
| BILL-EXT-03 | EXTERNAL | Non-blocking for build; blocking for VERIFIED | Field confirmation |

## Preconditions
Lock order documented in `billing/README` or module docstring and shared with BILL-WU-012/025/028.

## In-scope changes
Event application service; state transition functions; tests including out-of-order sequences.

## Explicit exclusions
Refund/void/reversal application; retries (BILL-WU-030); notifications (BILL-WU-033).

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/events.py`, `apps/backend/billing/services.py`; patterns `financials/views.py:83-97` (`select_for_update` within atomic), `process_ai_operations.py:109-120`.

## Data-integrity & security considerations
Exactly-once application relies on (a) the unique dedup key at receipt, (b) the terminal-state checks
under row lock, and (c) unique provider transaction ids on attempts. Any one of these alone is
insufficient, so all three are tested. Never activate from a redirect. Never trust payload amounts over
stored expectations.

## Failure modes
Crash mid-application (atomic; the event stays `received`; the worker retries); lock contention with a
renewal or cancellation (single lock order prevents deadlock); uncorrelated event (stored and alerted).

## Acceptance criteria
- **AC-BILL-021-1:** A SUCCESS for a checkout attempt activates the subscription on the plan with a period of exactly 30 days, and stores an agreement reference.
- **AC-BILL-021-2:** Applying the same event twice (bypassing receipt dedup) changes nothing the second time.
- **AC-BILL-021-3:** Sequences PENDING→SUCCESS, SUCCESS→PENDING and SUCCESS→FAILURE (same txn) end in succeeded; the latter is alerted and unapplied.
- **AC-BILL-021-4:** A `event=pay, status=FAILURE` payload is treated as failure.
- **AC-BILL-021-5:** An uncorrelated `merchantOrderId` changes no state and marks the event uncorrelated.
- **AC-BILL-021-6:** An amount or currency mismatch changes no state.
- **AC-BILL-021-7:** A simulated crash between state change and event marking leaves neither applied (transaction test).
- **AC-BILL-021-8:** Refund-type events are stored and not applied.

## Verification methods & required evidence
Unit plus integration tests; transaction/crash tests (`TransactionTestCase`); sandbox sequences via BILL-WU-036.

## Dependencies required before execution
BILL-WU-019, 020, 024, 029.

## Completion definition
AC-1..8 VERIFIED.

## Commit boundaries
`feat(billing): apply verified payment events transactionally`; `test(billing): cover event correlation, ordering and idempotent application`.

## Escalation conditions
Contradictory provider outcomes that need a money decision (reversal handling); any request to apply unverified or uncorrelated events.
