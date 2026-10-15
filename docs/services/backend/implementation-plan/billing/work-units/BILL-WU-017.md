# BILL-WU-017 — Payment-provider interface, fake provider, configuration and secrets

**ID:** BILL-WU-017 · **Workstream/Package:** BILL-WS-E / BILL-WP-E1
**Status:** READY
**Priority / Risk:** P0 / High (trust boundary)

## Purpose
Create the Madar-owned payment-provider contract (ADR-015 concern 2), separate from provider-neutral
billing decisions (concern 1), from the Kashier adapter (concern 3, BILL-WU-018), and from inbound
verification and translation (concern 4, consumed by BILL-WU-020). Ship a deterministic **fake provider**
so every billing flow can be built and tested without network or credentials.

## Expected outcome
`billing/providers/` (or `billing/providers.py`) with:
- An abstract `PaymentProvider` exposing Madar-shaped operations (names indicative):
  `create_recurring_setup_session(attempt, plan, return_url) -> CheckoutSession(session_url, provider_session_ref)`;
  `charge_saved_agreement(attempt, agreement_ref) -> ChargeResult(outcome ∈ {succeeded, failed, pending, unknown}, provider_ids, raw_code)`;
  `lookup_order(merchant_order_id) -> OrderStatus` (used by reconciliation);
  `verify_and_parse_webhook(raw_body: bytes, headers) -> VerifiedEvent | raises InvalidSignature`, which
  returns a **provider-neutral** `VerifiedEvent(dedup_key, kind, outcome_status, merchant_order_id, provider_txn_id, provider_order_id, amount, currency, agreement_ref?, mode, raw)`.
- A `FakePaymentProvider` with scriptable outcomes and HMAC-signed fake webhook generation, for tests.
- A factory `get_payment_provider()` selected by `settings.PAYMENT_PROVIDER` (`"fake"` default in DEBUG
  or test; `"kashier"` otherwise), following the `content/providers.py:102-112` and
  `ai/providers.py:136-142` factory shape. **No inheritance from, or reuse of, `VideoProvider`**, and no
  reuse of its `verify_webhook` stub (`content/providers.py:58,97-99`), per ADR-015 §Alternatives.
- Settings (names only; values via env): `PAYMENT_PROVIDER`, `KASHIER_MODE` (`test`|`live`),
  `KASHIER_MERCHANT_ID`, `KASHIER_PAYMENT_API_KEY_TEST`, `KASHIER_PAYMENT_API_KEY_LIVE`,
  `KASHIER_SECRET_KEY_TEST`, `KASHIER_SECRET_KEY_LIVE`, `KASHIER_API_BASE_*` (exact names are the
  implementer's). Kashier docs (reviewed 2026-10-15) state keys are mode-specific and can't be used across
  modes. **Production guard rails** in `config/settings.py`'s existing guard section: refuse to boot with
  `DEBUG=False` and `PAYMENT_PROVIDER=fake`, or with `PAYMENT_PROVIDER=kashier` missing the keys for the
  configured mode. `.env.example` gains **names only**, no values.

## Requirement / invariant references
ADR-015 (concerns 1-5); ADR-009; external-interfaces §Fourth interface; configuration-secrets principles; BD-26.

## Relevant ADRs / contracts
ADR-009, ADR-015, ADR-016 (verification is a prerequisite), ADR-017.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-001 | BLOCKING | Yes | App exists |

## Preconditions
Read ADR-015 in full; `config/settings.py:21-47` helpers and the production guard block.

## In-scope changes
Interface, fake, factory, settings, `.env.example` names, tests.

## Explicit exclusions
Real Kashier HTTP calls (BILL-WU-018); any endpoint; any persistence writes from the provider layer (the
provider returns results, billing services persist them; ADR-015 concern 5).

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/providers/`; `apps/backend/config/settings.py` (new settings near `:459`
`VIDEO_PROVIDER` and the guard block); `apps/backend/.env.example`.

## Data-integrity & security considerations
Secrets never logged (BILL-WU-035) and never included in exceptions. Constant-time signature compare
(`hmac.compare_digest`). The fake provider must be impossible to select in production (guard rail plus
test).

## Failure modes
Misconfigured mode (live keys in test, or the reverse; guarded); fake provider in prod (guarded).

## Acceptance criteria
- **AC-BILL-017-1:** All billing services depend only on `PaymentProvider` (static check: no `kashier` import outside the adapter package).
- **AC-BILL-017-2:** `verify_and_parse_webhook` on the fake rejects a tampered body and a wrong signature, and accepts a correctly signed one.
- **AC-BILL-017-3:** Booting with `DEBUG=False, PAYMENT_PROVIDER=fake` raises `ImproperlyConfigured` (test pattern like `config/tests.py:98-109`).
- **AC-BILL-017-4:** Booting with `PAYMENT_PROVIDER=kashier` and missing mode keys raises `ImproperlyConfigured`.
- **AC-BILL-017-5:** `.env.example` lists new variable names with empty values; no secret appears in the repo.
- **AC-BILL-017-6:** No class in `billing/providers` subclasses `content.providers.VideoProvider`.

## Verification methods & required evidence
Unit tests; subprocess settings tests (existing `config/tests.py` style); grep evidence.

## Dependencies required before execution
BILL-WU-001.

## Completion definition
AC-1..6 VERIFIED.

## Commit boundaries
`feat(billing): add payment-provider interface and fake provider`; `feat(config): add payment provider settings and production guards`; `test(billing): cover provider selection and guard rails`.

## Escalation conditions
Any proposal to reuse `VideoProvider`, or to put state transitions inside the provider layer.
