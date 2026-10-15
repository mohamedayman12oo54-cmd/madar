# BILL-WU-008 — Billing persistence foundation (DAT-5 logical concepts, integrity constraints)

**ID:** BILL-WU-008 · **Workstream/Package:** BILL-WS-B / BILL-WP-B1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open items:** exact subscription state names are not fixed by ADR-017 (the implementer proposes them,
and the proposal goes to review as a deviation record); invoice scope ("where required") is limited to
an internal amount-owed record because invoice/tax requirements are open (BILL-WU-040).
**Priority / Risk:** P0 / High (every money-state guarantee rests on these constraints)

## Purpose
Create the `billing` module's **private persistence** for the DAT-5 candidate concepts. DB-level
constraints must make the ADR-016/017 safety guarantees structurally true (not merely conventional),
and the persistence must stay strictly separate from `financials`.

## Expected outcome
Migrations in `apps/backend/billing/migrations/` creating persistence for these logical concepts
(authority: `docs/06-data/data-model.md` §Billing logical concepts; `docs/services/backend/06-data/data-model.md`
DAT-5). Physical names are the implementer's choice. The **integrity guarantees are mandatory**:

| Logical concept (DAT-5) | Mandatory integrity guarantees |
|---|---|
| Plan (catalog) | Global, not teacher-scoped; immutable identity key per plan; price stored as an integer minor-unit or `Decimal` with a currency code (EGP); `CHECK` price ≥ 0 |
| Subscription | **At most one per Environment** (DB unique on the environment reference, consistent with INV-9 and "one Teacher Environment has at most one active Subscription"); holds commercial state (trial or plan), current period bounds, trial start/end instants, `cancel_at_period_end` flag, a reference to the active recurring agreement; a version/updated-at for optimistic diagnostics |
| BillingPeriod | Belongs to a Subscription; `[start, end)` as aware datetimes with `end = start + 30 days` exactly (BILL-WU-024); **unique (subscription, period start)**; never derived from calendar months (`config/months.py` must not be imported) |
| Amount-owed record ("invoice" where required) | At most one per BillingPeriod (unique); amount and currency **copied from the Plan at creation** (server-decided, never client-supplied, mirroring `financials/serializers.py`'s server-authority pattern); status (open/satisfied/void-like). No tax or receipt fields |
| PaymentAttempt | Belongs to a Subscription (and to a BillingPeriod for renewals); a Madar-generated, unique, non-guessable **merchant order id** used as Kashier `merchantOrderId` (the correlation key); status (initiated/pending/succeeded/failed/ambiguous-style; final names in review); amount/currency expected; provider transaction/order ids (unique when present); **at most one non-terminal attempt per BillingPeriod** (partial unique index on Postgres). This is the double-charge guard for renewals |
| Recurring-agreement reference | Kashier card token + `agreementId` **references only**. Never a PAN or CVV. Stored as opaque strings. Mode (test/live) recorded so test tokens are never used live |
| Provider event record | Every **verified** inbound event; stores the raw body (or a hash plus the redacted body; see BILL-WU-035), the signature-verification result, mode, `event`, `data.status`, provider ids, received-at, processing status (received/processed/failed-to-apply/ignored-duplicate), attempts count, last error; **a unique dedup key** derived from provider identifiers (BILL-WU-020 defines the composition, at minimum `transactionId` + `status` + `event`). This is entirely separate from `ai.AIOperation.idempotency_key` (ADR-017) |
| Entitlement decision | **Not stored as a ledger** (DAT-5: "not itself a stored ledger"). It is computed by BILL-WU-010 |

Every scoped billing row carries the Environment reference. Use `environments.tenancy.TenantOwnedModel`
(`apps/backend/environments/tenancy.py:149-161`) for Subscription and its children, or an explicit
non-null FK to `environments.Environment`. Plan and Provider event are global (provider events are
correlated to a tenant only after verification and correlation).

## Requirement / invariant references
DAT-5; INV-9; functional §Billing; commercial-model §Plans/§Billing period; ADR-017 state separation; BND-1/BND-4.

## Relevant ADRs / contracts
ADR-014, ADR-016, ADR-017; `06-data/data-model.md` (Billing ≠ `Payment`).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-001 | BLOCKING | Yes | App exists |
| BILL-WU-006 | DATA | Non-blocking for authoring; blocking for launch (BILL-WU-037) | "One Subscription per Environment" equals "one per Teacher Account" only once INV-9 is DB-enforced |

## Preconditions
Read DAT-5 and ADR-017 in full. Confirm PostgreSQL in tests (partial unique indexes need it; `settings.py:166-176`).

## In-scope changes
`billing/models.py` (or a `models/` package), migrations, model-level `clean()` where helpful, Django admin
registration as **read-only** (optional; no money-moving actions in admin).

## Explicit exclusions
Plan rows/data (BILL-WU-009); any service logic; refunds, proration, tax fields; any FK from
`financials` to `billing` or the reverse; storing card numbers.

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/models.py`, `apps/backend/billing/migrations/0001_initial.py`. Patterns:
`financials/models.py:32-37` (UniqueConstraint/CheckConstraint style), `ai/models.py:77-87` (partial
unique via `condition=Q(...)`), `environments/tenancy.py:149-161`.

## Data-integrity & security considerations
Money fields are never client-writable. Provider ids get unique constraints so a replay can't create a
second attempt. Cascade semantics: deleting an Environment cascades to `TenantOwnedModel` rows today.
For financial records consider `PROTECT` for PaymentAttempt and Provider event, because data is never
destroyed under access-not-granted. Choose deliberately, and record the choice in the PR. The raw
webhook body may contain cardholder name and masked card (`data.card.cardInfo`), so minimise or redact
it (BILL-WU-035).

## Failure modes
Constraint missing so a replay double-applies (prevented by tests); timezone-naive datetimes
(USE_TZ=True; tests assert aware); a Subscription without an Environment.

## Acceptance criteria
- **AC-BILL-008-1:** Creating two Subscriptions for one Environment raises `IntegrityError`.
- **AC-BILL-008-2:** Creating two non-terminal PaymentAttempts for the same BillingPeriod raises `IntegrityError`; a second attempt after the first is terminal is allowed.
- **AC-BILL-008-3:** Two provider-event rows with the same dedup key raise `IntegrityError`.
- **AC-BILL-008-4:** Duplicate merchant order ids and duplicate provider transaction ids are rejected.
- **AC-BILL-008-5:** Two BillingPeriods with the same (subscription, start) are rejected.
- **AC-BILL-008-6:** No billing model has a field capable of holding a PAN or CVV, and the recurring-agreement reference stores opaque token/agreement strings only (review checklist plus a test that the model has no such named fields).
- **AC-BILL-008-7:** No import of `financials` or `config.months` exists in `billing/` (static test or grep in CI-like check).
- **AC-BILL-008-8:** Migrations apply and reverse on an empty PostgreSQL test DB.

## Verification methods & required evidence
Model/constraint tests against PostgreSQL; migration rehearsal; code review record for the cascade choice and state names.

## Dependencies required before execution
BILL-WU-001.

## Completion definition
AC-1..8 VERIFIED; state-name proposal recorded as a reviewed deviation note.

## Commit boundaries
`feat(billing): add billing persistence models and constraints`; `test(billing): cover billing persistence integrity constraints`.

## Escalation conditions
A need to store anything card-like; a need to reference `financials`; any requirement for invoice/tax
fields; any wish to persist the entitlement decision as authoritative state (DAT-5 says derived).
