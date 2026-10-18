# Scope — BILL-PLAN-01

> Derived from `docs/01-product/commercial-model.md`, `docs/02-requirements/functional.md` §Billing,
> INV-9, ADR-013..018, DAT-5, and the two root audits. Code citations are at commit `bf115df`.

## 1. In scope

| # | Area | Authority | Units |
|---|---|---|---|
| S-01 | Repair the baseline so the Backend can boot and its existing suite can run (phantom `billing` app registration) | ADR-014; BILL-RISK-01 | BILL-WU-001, 002 |
| S-02 | Enforce INV-9 (one Teacher Account : one Environment) at ORM and DB level, with a pre-migration data check and a gated remediation path | INV-9, ADR-013 §Consequences, TAL-2 | BILL-WU-003..007 |
| S-03 | `billing` bounded module with private persistence for the DAT-5 logical concepts | ADR-014, DAT-5, BND-4 | BILL-WU-001, 008 |
| S-04 | Plan catalog (3 plans, prices, caps, feature keys) | commercial-model §Plans | BILL-WU-009 |
| S-05 | Billing-owned entitlement contract plus Backend enforcement after tenant/authz resolution | ADR-018, TAL-5, security-authz | BILL-WU-010, 011, 012, 013 |
| S-06 | 16-day trial starting atomically at signup | commercial-model §Free trial; functional §Billing | BILL-WU-014, 015, 016 |
| S-07 | Madar-owned payment-provider interface, Kashier adapter, secrets/config | ADR-015, ADR-009, configuration-secrets | BILL-WU-017, 018 |
| S-08 | Checkout initiation, correlation, and the redirect-is-not-proof rule | ADR-016 trust distinctions, AL-3 | BILL-WU-019 |
| S-09 | The single approved inbound webhook: verification, durable receipt, dedup, transactional application, recovery | ADR-016, ADR-017 | BILL-WU-020, 021, 022 |
| S-10 | Reconciliation of ambiguous, delayed or missed outcomes | ADR-017 §Reconciliation; commercial-model §Failed renewal | BILL-WU-023 |
| S-11 | 30-elapsed-day billing periods and the renewal execution capability; production activation gated externally | commercial-model §Billing period; BILL-EXT-01 | BILL-WU-024, 025, 026, 027 |
| S-12 | Cancel-at-period-end with renewal race safety | commercial-model §Cancellation | BILL-WU-028 |
| S-13 | Failed-payment outcome recording (foundation); retry/grace execution gated on decision | commercial-model §Failed renewal | BILL-WU-029, 030 |
| S-14 | Teacher-facing billing API, Frontend contract hand-off, billing notifications (gated) | AL-4, api-contract | BILL-WU-031, 032, 033 |
| S-15 | Security/adversarial tests, observability/redaction, sandbox → staging → production verification | OP-PARITY, AL-3, Kashier go-live | BILL-WU-034..037 |

## 2. Out of scope

| Item | Why | Tracked as |
|---|---|---|
| Frontend implementation (checkout UI, billing screens, restricted-access UI) | Frontend-owned; Backend delivers a contract only | BILL-WU-032 (hand-off only) |
| Refunds | Policy open (commercial-model §Open items) | BILL-WU-038 (OUT OF SCOPE) |
| Upgrade/downgrade timing, proration | Policy open | BILL-WU-039 (OUT OF SCOPE) |
| Invoice/receipt/tax documents | Policy and legal open | BILL-WU-040 (OUT OF SCOPE); BILL-WU-008 keeps only an internal "amount owed per period" record |
| AI usage quotas / cost controls | Policy open | BILL-WU-041 (OUT OF SCOPE) |
| Price-change treatment for existing subscribers | Policy open | BILL-WU-042 (OUT OF SCOPE) |
| Mechanism for the Plan 3 "separately-priced future feature" rule | Mechanism open (commercial-model §Plan 3) | `traceability-matrix.md` gap G-03 |
| Any other inbound integration (including activating `content/providers.py` `verify_webhook` for a video vendor) | ADR-016 is Kashier-only and is not precedent | Exclusion in BILL-WU-020 |
| Any change to `financials` (`MonthlyPayment`) | Different concept (access-lifecycle.md §Distinct) | Exclusion in every unit |
| New broker/queue (Celery/RQ/etc.) | ADR-012; existing management-command worker pattern is sanctioned | Exclusion in BILL-WU-022/023/025 |
| Choosing a scheduler, host, CI vendor, or secret store | Operations-owned | BILL-OPS-01; BILL-WU-027 |
| Dead `apps/web/src/lib/financialsApi.js` cleanup | Frontend-owned (AL-4) | BILL-RISK-12 note |

## 3. Existing capabilities to reuse (pattern reuse, not code reuse, unless stated)

| Capability | Where (verified at `bf115df`) | How it is reused | Caveat |
|---|---|---|---|
| Provider-interface pattern (ADR-009) | `apps/backend/content/providers.py:44-112` (`VideoProvider`, `_PROVIDERS`, `get_provider()`); `apps/backend/ai/providers.py:136-142` | **Shape only:** abstract base + settings-selected factory (`PAYMENT_PROVIDER`) | **Do not reuse `VideoProvider` or its `verify_webhook`.** `LocalStorageProvider.verify_webhook` returns `False` unconditionally (`content/providers.py:97-99`), which is wrong for payments (ADR-015) |
| Atomic-claim polling worker | `apps/backend/ai/management/commands/process_ai_operations.py:35-43` (conditional-UPDATE claim), `:66-69` (stale requeue), `--loop/--interval/--max-iterations` | Template for `process_billing_events`, `reconcile_billing_attempts`, `process_billing_renewals` | **Do not copy `notifications/management/commands/process_notifications.py`.** It has no claim step (`:43-58`) and double-sends under concurrency (audit R3) |
| Provider call outside transaction, outcome inside | `process_ai_operations.py:80-120` | Renewal charge: claim in txn → call provider outside txn → persist outcome in txn | — |
| Server-derived tenant context | `apps/backend/environments/tenancy.py:65-128` (`resolve_environment`, `IsEnvironmentMember`, `request.environment`) | Entitlement check runs **after** this resolves (ADR-018) | Webhook endpoint has no tenant header; it resolves Environment from the correlated internal record, never from payload claims |
| Tenant test harness | `apps/backend/environments/tenancy_testing.py:16-71` (`TenantTestCase`, `with_env`, `assert_cross_tenant_denied`) | All billing API tests | Harness creates one env per teacher, so it is already INV-9-compatible |
| Adversarial suite structure | `apps/backend/config/test_security_audit.py` (classes `HorizontalPrivilegeTests`, `VerticalPrivilegeTests`, `InjectionAndInputTests`, `SecretsAndErrorLeakTests`, …) | Model for `billing` adversarial tests (BILL-WU-034) | — |
| Stable error envelope | `apps/backend/config/exceptions.py:5-44` (`{"detail","code"}`) | Billing errors raise `APIException` subclasses with stable `default_code` (e.g., `entitlement_required`, `student_cap_reached`) | Wire taxonomy is still NODE-WireAPI; the code names are proposals to hand off (BILL-WU-032) |
| Env-driven settings + boot guard rails | `apps/backend/config/settings.py:21-47` (`env_str/env_bool/env_int`), production guards `:60-99` | `PAYMENT_PROVIDER`, `KASHIER_MODE`, mode-specific keys; refuse to boot in production with test-mode keys or missing secrets | — |
| Race-safe write pattern | `apps/backend/financials/views.py:83-97` (`transaction.atomic` + `select_for_update` + IntegrityError retry) | Subscription state writes lock the Subscription row | Built for single-admin races; billing needs a documented lock order (BILL-WU-021/028) |
| Atomic signup transaction | `apps/backend/accounts/views.py:174-191` (`TeacherSignupEnvironmentView.post`) | Trial creation joins this transaction (BILL-WU-014) | — |

## 4. Missing capabilities to build

`billing` app package and migrations; Plan catalog; Subscription / BillingPeriod / PaymentAttempt /
internal amount-owed record / provider-event record / recurring-agreement reference; entitlement
contract; entitlement permission class; student-cap guard; payment-provider interface plus fake and
Kashier implementations; outbound HTTP client usage (no `requests`/`httpx` is pinned in
`requirements.txt`, so the stdlib-vs-dependency choice is an implementation decision inside BILL-WU-018);
checkout endpoint; webhook endpoint with raw-body HMAC verification; event application; three worker
commands; billing API namespace `/api/v1/billing/`; billing adversarial tests; billing log redaction.

## 5. Capabilities to modify

| Surface | Change | Unit |
|---|---|---|
| `apps/backend/config/settings.py:126` | The `"billing"` entry must resolve to a real app (or be confirmed) | BILL-WU-001 |
| `apps/backend/environments/models.py:14-22` | `owner` ForeignKey → OneToOneField; docstring "A teacher may own several" replaced | BILL-WU-006 |
| `apps/backend/environments/migrations/` | New migration `0002_*` (first change since `0001_initial.py`) | BILL-WU-006 |
| `apps/backend/environments/tests.py:15-40`, `test_phase1_tenancy.py:139-150`, `accounts/management/commands/seed_demo.py:39-46` | Stop creating multiple Environments per teacher | BILL-WU-005 |
| `apps/backend/accounts/views.py:174-191` | Call the Billing `start_trial` capability inside the existing atomic block | BILL-WU-014 |
| AI submit views (`apps/backend/ai/urls.py`, `studentarea/urls.py:16-21`) and the AI worker | Entitlement capability checks (plan-gated AI) on Web and Worker paths | BILL-WU-011 |
| `apps/backend/academics/views.py:101-147` (`EnrollmentListCreateView.post`), `EnrollmentDetailView` (re-activation) | Student-cap guard | BILL-WU-012 |
| `apps/backend/config/urls.py:23-38` | Add `api/v1/billing/` | BILL-WU-031 |
| `apps/backend/.env.example` | Document new variable **names** only | BILL-WU-017 |

**Not modified:** `accounts/authentication.py` (`MadarJWTAuthentication.get_user`, lines 17-29). ADR-018
forbids putting entitlement there. `financials/*`. `notifications/models.py` (catalog change is
BILL-DEC-06).

## 6. Integration boundaries

```
Teacher browser ──JWT──► /api/v1/billing/* (Web) ──► billing services ──► PaymentProvider (outbound) ──► Kashier
Teacher browser ◄──redirect (UX only, NO trust)── Kashier hosted page
Kashier ──signed POST──► /api/v1/billing/webhooks/kashier/ (the ONLY inbound integration, ADR-016)
Worker (manage.py process_billing_events | reconcile_billing_attempts | process_billing_renewals)
     └── same trust/tenant guarantees as Web (OP-PARITY); Environment derived from internal records only
Other modules ──► billing entitlement capability (BND-1/BND-4); never read billing tables directly
billing ──► Identity & Enrollment / environments capability (which Environment; active enrollment count)
```

## 7. Operational dependencies

PostgreSQL test DB (BILL-OPS-02); a production scheduler for three worker commands (BILL-OPS-01, none
exists: `infra/`, `scripts/`, `.github/` hold only `.gitkeep`, rechecked 2026-10-15); secret
injection for mode-specific Kashier keys (Operations, `configuration-secrets.md`); a public HTTPS
webhook URL per environment and mode; an egress IP allow-list if Kashier's Secret Key IP restriction is
used; DB backup/PITR before the cardinality migration runs on shared DBs.

## 8. Frontend hand-offs (contract only — BILL-WU-032)

Plan discovery; trial/subscription status (days remaining, period end); checkout initiation and the
"pending confirmation" state after redirect (redirect ≠ paid); billing history; cancel-at-period-end
status; `entitlement_required` / `student_cap_reached` / capability-unavailable responses;
restricted-access UI (blocked on BILL-DEC-02); the fact that `GET /api/v1/environments/teacher/` keeps a
list shape but will never contain more than one item.

## 9. External-provider dependencies (Kashier)

BILL-EXT-01 (exact 30-elapsed-day recurring compatibility; **launch/design gate**); BILL-EXT-02
(sandbox merchant credentials); BILL-EXT-03 (confirmation of signature key, payload, token/agreement
fields and status-lookup API); BILL-EXT-04 (live merchant activation and go-live checklist);
BILL-EXT-05 (recurring-agreement consent requirements). Detail in `risks-and-open-issues.md`.
