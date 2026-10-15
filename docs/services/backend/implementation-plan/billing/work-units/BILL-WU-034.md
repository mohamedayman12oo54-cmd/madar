# BILL-WU-034 — Billing adversarial/security test suite

**ID:** BILL-WU-034 · **Workstream/Package:** BILL-WS-J / BILL-WP-J1
**Status:** READY
**Priority / Risk:** P0 / High

## Purpose
Extend the repo's adversarial testing practice (`apps/backend/config/test_security_audit.py`, classes
`HorizontalPrivilegeTests`, `VerticalPrivilegeTests`, `InjectionAndInputTests`, `AISecurityTests`,
`SecretsAndErrorLeakTests`, `AuthenticationHardeningTests`, `ProductionConfigTests`) to the new billing
attack surface, as one consolidated suite that is part of `manage.py test`.

## Expected outcome
`apps/backend/billing/test_security.py` (or new classes in `config/test_security_audit.py`) built on the
`_Fixture(TenantTestCase)` pattern (`test_security_audit.py:28`), covering:
- **Horizontal:** teacher B reading, cancelling or checking out on A's environment via header; guessing attempt ids.
- **Vertical:** students and parents (`parents.auth.ParentSessionAuthentication`) reaching billing endpoints.
- **Webhook forgery:** unsigned, wrong-key, other-mode-key, tampered, oversized, replayed old valid events, `event="idempotency"` replays, uncorrelated `merchantOrderId`, amount mismatch.
- **Redirect spoofing:** the return endpoint with "success" parameters changes nothing.
- **Mass assignment:** price, amount, plan cap, status, environment fields in checkout and cancel bodies.
- **Leakage:** tokens, agreement ids, secrets and raw payloads never in responses or error bodies; 500s are generic (`config/urls.py:14-17`).
- **Entitlement bypass:** gated AI submission via alternative routes (teacher and student paths); worker parity.
- **Inbound surface guard:** the set of `AllowAny` views equals the expected set (single new webhook).

## Requirement / invariant references
ADR-016, ADR-017, ADR-018; INV-7; OP-PARITY; AL-3.

## Relevant ADRs / contracts
ADR-004/008/010; `apps/backend/SECURITY-AUDIT.md` (existing suite description).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-011, 019, 020, 021, 028, 031 | VERIFICATION | Yes | Surfaces under test |

## Preconditions
Fake provider can sign fixtures with test keys.

## In-scope changes
Test code only.

## Explicit exclusions
Penetration testing against live Kashier.

## Implementation surfaces (grounded at bf115df)
`apps/backend/config/test_security_audit.py` (pattern); `apps/backend/environments/tenancy_testing.py:57-71` (`assert_cross_tenant_denied`).

## Data-integrity & security considerations
Test keys only; never real secrets in fixtures.

## Failure modes
Suite drift as endpoints evolve (the AllowAny enumeration test catches new inbound routes).

## Acceptance criteria
- **AC-BILL-034-1:** Every attack category above has at least one test, and all pass.
- **AC-BILL-034-2:** The `AllowAny` enumeration test fails if any additional unauthenticated route is added.
- **AC-BILL-034-3:** `SECURITY-AUDIT.md`'s inventory is updated by the implementer to list the new tests (documentation in `apps/backend`, as part of implementation).

## Verification methods & required evidence
Suite run output.

## Dependencies required before execution
BILL-WU-011, 019, 020, 021, 028, 031.

## Completion definition
AC-1..3 VERIFIED.

## Commit boundaries
`test(billing): add billing adversarial security suite`; `docs(security): list billing adversarial tests`.

## Escalation conditions
A test reveals a design-level weakness (e.g., correlation key guessable).
