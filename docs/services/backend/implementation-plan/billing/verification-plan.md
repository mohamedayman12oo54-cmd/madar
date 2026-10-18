# Verification Plan — BILL-PLAN-01

> **No tests were executed during the authoring of this plan.** Every test below is still to be authored
> and executed during implementation. The plan inherits **Implemented ≠ Verified** from
> `../verification.md`: a unit is VERIFIED only when its ACs are demonstrated with the evidence listed here.

## 1. Verification objectives

| # | Objective | Primary units |
|---|---|---|
| VO-1 | The baseline boots and the existing suite stays green throughout (no regression) | 001, 002, all |
| VO-2 | INV-9 holds at the DB level, and no shared DB is migrated while non-compliant | 003-007 |
| VO-3 | Money and state integrity: no double application, no double charge, no activation without a verified trusted signal | 008, 019-025, 028, 029 |
| VO-4 | ADR-016's boundary: exactly one new unauthenticated inbound route, signature-verified, nothing else | 020, 034 |
| VO-5 | ADR-017 separation: provider-event dedup is independent of AI `idempotency_key` | 008, 020, 021 |
| VO-6 | ADR-018: entitlement enforced after tenant resolution, outside authentication, on Web and Worker | 010, 011, 012 |
| VO-7 | Commercial rules exactly as decided (16 days, 30 elapsed days, 250/400/800/none, three prices), and nothing undecided defaulted | 009, 010, 012, 014, 024, 025, 029 |
| VO-8 | Tenant isolation is unaffected by billing (INV-7) | 011, 019, 028, 031, 034 |
| VO-9 | No secrets or card data in code, logs, responses | 017, 018, 035, 034 |
| VO-10 | Provider facts confirmed in sandbox, then live behaviour confirmed by smoke | 036, 026, 037 |

## 2. Test levels (to be authored)

| Level | Tooling (existing) | Used for |
|---|---|---|
| Unit | `django.test.TestCase` via `accounts.testing.TestCase` (`apps/backend/accounts/testing.py:12-15`, which clears throttle cache) | entitlement decisions (frozen clock), period math, signature verification, outcome mapping |
| Integration (API) | `environments.tenancy_testing.TenantTestCase` (`with_env`, `assert_cross_tenant_denied`, two teachers with one env each) | checkout, cancel, read API, enforcement, webhook endpoint |
| Constraint/DB | PostgreSQL test DB (mandatory: `settings.py:166-176`) | unique and partial-unique indexes, OneToOne, migration forward/reverse |
| Concurrency | `django.test.TransactionTestCase` with two DB connections/threads | renewal claim, cancel-vs-renewal race, student cap, worker claims |
| Crash/recovery | Fault injection between steps (patch to raise) | event application atomicity, stale `processing` → `unknown` |
| Command | `call_command(..., max_iterations=1)` (pattern from the AI worker flags) | `process_billing_events`, `reconcile_billing_attempts`, `process_billing_renewals`, `check_environment_cardinality` |
| Settings/boot | Subprocess settings tests (pattern: `apps/backend/config/tests.py:98-109`) | production guard rails for payment config |
| Adversarial | Classes mirroring `config/test_security_audit.py` (`_Fixture(TenantTestCase)`) | BILL-WU-034 |
| Static/structural | Tests that grep, inspect or enumerate URL patterns | no `billing` import in `accounts/authentication.py`; no `config.months` import; no `AIOperation`/`idempotency_key` in billing; `AllowAny` route set; permission ordering |
| Sandbox integration | Kashier test mode on a public staging URL | BILL-WU-036 |
| Staging | Full lifecycle in staging with schedulers | BILL-WU-027, 037 |
| Production smoke | Live small transaction per Kashier go-live list | BILL-WU-037, 026 AC-3 |

## 3. The four kinds of verification, kept separate

1. **Tests to be authored** are the AC-linked tests in each WU file (§4). Authoring a test is not running it.
2. **Tests to be executed during implementation:** each PR runs the **full** suite on PostgreSQL (there is no
   CI, BILL-RISK-10), and attaches output with SHA, counts and DB version. BILL-WU-002 sets the baseline.
3. **Sandbox integration verification** (BILL-WU-036) needs BILL-EXT-02 and BILL-OPS-04. It converts the
   provider-dependent ACs (AC-BILL-018-6; 019/020/021/023/025 sandbox parts) from IMPLEMENTED to VERIFIED and
   records BILL-EXT-03 answers. It can't prove the 30-day interval.
4. **Staging verification and production smoke/go-live checks** (BILL-WU-027, 007, 037, 026 AC-3) produce
   operational records, not test output.

## 4. Acceptance-criteria linkage

| Unit | ACs | Level(s) | Evidence |
|---|---|---|---|
| 001 | AC-BILL-001-1..3 | boot check | command output; PR note |
| 002 | AC-BILL-002-1..2 | full suite | test log |
| 003 | AC-BILL-003-1..6 | command/unit; ops run | tests; per-DB report |
| 004 | AC-BILL-004-1..3 | ops | approval record; before/after reports; row-count diff |
| 005 | AC-BILL-005-1..4 | integration; command | suite log; cardinality report after seed |
| 006 | AC-BILL-006-1..7 | constraint; integration; migration rehearsal | tests; rehearsal log |
| 007 | AC-BILL-007-1..3 | ops | per-DB ops records |
| 008 | AC-BILL-008-1..8 | constraint; static | tests; review record |
| 009 | AC-BILL-009-1..3 | unit/data-migration | tests; review |
| 010 | AC-BILL-010-1..7 | unit (frozen clock); static | tests |
| 011 | AC-BILL-011-1..8 | integration; command; static | tests |
| 012 | AC-BILL-012-1..5 | integration; concurrency | tests |
| 013 | AC-BILL-013-1..3 | integration | tests (after BILL-DEC-02) |
| 014 | AC-BILL-014-1..6 | integration; fault injection | tests |
| 015 | AC-BILL-015-1..3 | command; ops | tests; staging/prod logs |
| 016 | AC-BILL-016-1 | integration | tests; decision record |
| 017 | AC-BILL-017-1..6 | unit; settings/boot; static | tests |
| 018 | AC-BILL-018-1..6 | unit (synthetic); sandbox | tests; sandbox record |
| 019 | AC-BILL-019-1..7 | integration; adversarial | tests; sandbox record |
| 020 | AC-BILL-020-1..7 | integration; static; adversarial | tests; sandbox record |
| 021 | AC-BILL-021-1..8 | integration; crash | tests; sandbox record |
| 022 | AC-BILL-022-1..4 | command; concurrency | tests |
| 023 | AC-BILL-023-1..5 | command; concurrency | tests; sandbox record |
| 024 | AC-BILL-024-1..4 | unit; static | tests |
| 025 | AC-BILL-025-1..7 | command; concurrency; crash | tests; sandbox record |
| 026 | AC-BILL-026-1..3 | external; sandbox; prod | Kashier written answer; logs; first-cycle record |
| 027 | AC-BILL-027-1..3 | staging ops | ops records |
| 028 | AC-BILL-028-1..6 | integration; concurrency | tests |
| 029 | AC-BILL-029-1..4 | unit/integration | tests |
| 030 | AC-BILL-030-1..2 | frozen clock; sandbox | tests (after BILL-DEC-05) |
| 031 | AC-BILL-031-1..4 | integration | tests |
| 032 | AC-BILL-032-1..4 | review | document; acknowledgment |
| 033 | AC-BILL-033-1 | integration | tests (after BILL-DEC-06) |
| 034 | AC-BILL-034-1..3 | adversarial | suite log |
| 035 | AC-BILL-035-1..3 | log capture; review | tests; runbook |
| 036 | AC-BILL-036-1..3 | sandbox | sandbox record |
| 037 | AC-BILL-037-1..4 | staging; prod smoke | ops/go-live records |
| 038-042 | AC-BILL-038-1 … AC-BILL-042-1 | review | review notes (scope guards) |

## 5. Test data, fixtures, isolation constraints

- **Use `TenantTestCase`** for every API test. Its fixture is already INV-9-compatible (one env per
  teacher, `tenancy_testing.py:26-38`). New billing fixtures add a Subscription per environment via
  Billing services, never via raw inserts into another module's tables (BND-1).
- **Clock:** inject `now` into entitlement and period functions. For views, patch `django.utils.timezone.now`
  at a single seam. Never `sleep` in tests.
- **Provider:** `PAYMENT_PROVIDER=fake` in tests. Webhook fixtures are signed by the fake with a test-only
  key defined in the test module. No real Kashier key in the repo. Network calls are forbidden in the suite
  (the fake transport asserts if the real adapter tries to connect).
- **PostgreSQL is required.** Partial unique indexes and `select_for_update` semantics differ elsewhere, and
  settings refuse non-Postgres anyway. Concurrency tests need `TransactionTestCase`.
- **Throttle isolation:** inherit `accounts.testing.TestCase` (cache cleared per test).
- **No PII in fixtures beyond synthetic names/phones** (pattern: existing tests).
- **Cardinality migration rehearsal** runs on a disposable DB loaded with a deliberate duplicate.

## 6. Provider sandbox verification (BILL-WU-036)

Preconditions: BILL-EXT-02 (test-mode account and keys), BILL-OPS-04 (public HTTPS URL). Scope: setup
session, hosted payment with test cards (success and decline), setup webhook, token and agreement storage,
pay-with-token, decline webhook, redelivery and duplicate handling, status lookup, wrong-key rejection.
Evidence: redacted logs, DB snapshots, Kashier dashboard exports, and the BILL-EXT-03 answers. **Not
provable in sandbox:** the 30-elapsed-day interval guarantee (BILL-EXT-01). That needs Kashier's written
confirmation.

## 7. Staging verification

All migrations applied (including 007 on the staging DB after a zero-duplicate check); billing workers
scheduled for 72 h (BILL-WU-027); full lifecycle signup → trial → checkout → activation → renewal (forced
due by data setup) → cancel → end; adversarial suite green against the staging build; log redaction spot-check.

## 8. Production smoke / go-live checks

Per BILL-WU-037: Kashier go-live checklist (live keys per mode, live webhook, IP allow-list, payment methods);
one internal live transaction confirmed via **order reconciliation, not redirect**; webhook verified with the
live key; Subscription activated with a 30-day period; manual dashboard refund by Operations (Madar refunds
are OUT OF SCOPE); settlement window observed. First live renewal cycle observed under BILL-WU-026 AC-3.

## 9. Evidence required before a unit may be marked VERIFIED

1. Every AC in the unit file is linked to a passing test or an ops/external record.
2. Full-suite PostgreSQL run attached for the commit that completes the unit (no CI exists, so manual
   attachment is required).
3. For provider-dependent ACs: BILL-WU-036 record referenced.
4. For READY WITH A TRACKED OPEN ITEM units: the open item is visibly unresolved in code (TODO/flag citing
   its ID) and in `risks-and-open-issues.md`. Resolving it silently disqualifies VERIFIED.
5. For BLOCKED units: the unblocking decision or external record is linked.
6. Reviewer sign-off naming the reviewer.

## 10. Regression-critical checks (run on every billing PR)

Existing tenant/security suites (`config/test_security_audit.py`, `environments/test_phase0_security.py`,
`environments/test_phase1_tenancy.py`); signup suite (`accounts/tests.py`); financials suite (proves
`financials` is untouched); AI idempotency tests (`ai/tests.py` `SelectiveIdempotencyTests`) unchanged and
green, which proves ADR-011 is intact.
