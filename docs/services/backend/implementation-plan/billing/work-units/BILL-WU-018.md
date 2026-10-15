# BILL-WU-018 — Kashier adapter (outbound: save-token session, pay-with-token, status lookup; inbound verification)

**ID:** BILL-WU-018 · **Workstream/Package:** BILL-WS-E / BILL-WP-E1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open items:** BILL-EXT-02 (sandbox merchant credentials needed to verify, not to write, the adapter);
BILL-EXT-03 (exact signature key, payload and token/agreement fields, status-lookup endpoint semantics);
BILL-EXT-01 (which `paymentFrequency`/`minimumDaysBetweenPayments` values express a 30-elapsed-day
cadence; left as configuration, **not** defaulted to `MONTHLY`).
**Priority / Risk:** P0 / High

## Purpose
Implement `PaymentProvider` for Kashier (ADR-015 concerns 3 and 4) against Kashier's published contract,
with every Kashier-specific fact isolated in this adapter and verified in sandbox (BILL-WU-036).

## Expected outcome
`billing/providers/kashier.py` implementing:
- **Recurring setup session.** Per Kashier's recurring guide (reviewed 2026-10-15): `POST /v3/payment/sessions`
  on the mode-specific host, with an `agreement` object (`type=RECURRING`, `paymentFrequency`,
  `minimumDaysBetweenPayments`, `expiryDate`, `amountVariability`, `maximumAmountPerPayment`,
  `numberOfPayments`), `saveCard`, `interactionSource=RECURRING`, `merchantOrderId` = Madar's attempt order
  id, and `serverWebhook` = Madar's webhook URL. It returns `sessionUrl`. **All agreement values come from
  configuration, and the 30-day-relevant ones stay unset/required until BILL-EXT-01 resolves.** The adapter
  refuses to create a live-mode agreement if they are unset.
- **Charge saved token.** `POST /v3/orders` on the FEP host, `apiOperation=PAY`, `paymentMethod.card.cardToken`,
  `paymentMethod.card.agreement.id`, `interactionSource=CONTAUTH`, the `Kashier-Hash` header computed per
  docs (including the `.{customerReference}` suffix rule). Maps responses to `succeeded`/`failed`/`pending`/`unknown`.
  **A timeout or transport error maps to `unknown`, never `failed`** (an ambiguous outcome; BILL-WU-023).
- **Status lookup** for reconciliation. Exact endpoint is BILL-EXT-03; implement behind `lookup_order` and
  verify in sandbox.
- **Webhook verification.** HMAC-SHA256 hex over `data.signatureKeys` (sorted; values URL-encoded;
  `k=v` joined by `&`), compared to the `x-kashier-signature` header with constant-time compare, using the
  **mode-specific Payment API Key** (docs say the same key as the Payment Hash; to be confirmed,
  BILL-EXT-03). Branch on `data.status` (`SUCCESS`/`FAILURE`/`PENDING`), **not** on `event`. Treat
  `event="idempotency"` (replay notification) as a duplicate signal. Translate to `VerifiedEvent`. Token
  and agreement fields (the docs are inconsistent between `cardDataToken` and `cardToken`) are parsed
  defensively and confirmed in sandbox.
- HTTP client: `requests`/`httpx` is not pinned (`apps/backend/requirements.txt`). Either use stdlib
  `urllib.request` with explicit timeouts, or add a pinned dependency as a reviewed `build(backend):`
  commit. Every call has a timeout and never runs inside a DB transaction (pattern: `process_ai_operations.py:15`).

## Requirement / invariant references
ADR-015 concerns 3-4; ADR-016 prerequisite 1; ADR-017 (verification before dedup); external-interfaces §Fourth interface; commercial-model §External verification context.

## Relevant ADRs / contracts
ADR-015, ADR-016, ADR-017.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-017 | CONTRACT | Yes | Implements the interface |
| BILL-EXT-02 | EXTERNAL | Non-blocking for authoring (unit tests use recorded/synthetic fixtures); blocking for VERIFIED | Sandbox access |
| BILL-EXT-03 | EXTERNAL | Same | Field and key confirmation |
| BILL-EXT-01 | EXTERNAL | Blocking only for live agreement creation | 30-day cadence values |

## Preconditions
Re-read the four Kashier pages at execution time and record the review date. Facts may have changed.

## In-scope changes
Adapter module, request signing, response mapping, defensive parsing, unit tests with synthetic fixtures (signed with a test key).

## Explicit exclusions
Persisting anything; choosing the 30-day agreement parameters; refunds, voids, bulk charge (bulk charge
is a per-merchant flag per Kashier docs and is not used).

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/providers/kashier.py`; possibly `apps/backend/requirements.txt` (only if a client
library is chosen).

## Data-integrity & security considerations
Never log full request or response bodies (the card holder name and masked card appear in payloads);
redact keys. Separate test and live keys; the adapter asserts that the event's mode matches the
configured mode.

## Failure modes
Network timeout during charge, where the money may or may not have moved (→ `unknown`, then reconcile);
signature-scheme drift (sandbox test catches it); wrong-mode key (verification fails closed).

## Acceptance criteria
- **AC-BILL-018-1:** A synthetic webhook signed per the documented scheme verifies; altering any signed value or the signature fails.
- **AC-BILL-018-2:** Charge transport timeout yields `unknown`, not `failed`.
- **AC-BILL-018-3:** Outcome mapping uses `data.status`; a payload with `event=pay, status=FAILURE` maps to failed.
- **AC-BILL-018-4:** Live-mode setup session creation is refused while BILL-EXT-01 agreement parameters are unset.
- **AC-BILL-018-5:** No outbound call occurs inside `transaction.atomic()` (test with a fake transport asserting `connection.in_atomic_block` is False).
- **AC-BILL-018-6 (sandbox, via BILL-WU-036):** Real sandbox session, charge, lookup and webhook verification succeed.

## Verification methods & required evidence
Unit tests with synthetic fixtures (AC-1..5); sandbox evidence (AC-6).

## Dependencies required before execution
BILL-WU-017.

## Completion definition
AC-1..5 VERIFIED; AC-6 VERIFIED via BILL-WU-036. Until then, status remains IMPLEMENTED, not VERIFIED.

## Commit boundaries
`feat(billing): add Kashier payment-provider adapter`; `test(billing): cover Kashier signing, verification and outcome mapping`; optional `build(backend): pin HTTP client for payment provider`.

## Escalation conditions
Sandbox behaviour contradicts the docs; Kashier requires storing anything card-like; agreement parameters can't express 30 elapsed days (→ BILL-EXT-01 outcome, escalate to product).
