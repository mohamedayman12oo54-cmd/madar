# Work Breakdown — BILL-PLAN-01

> 11 Workstreams (A–K) → 18 Work Packages → 42 Work Units. Each unit has a full spec in
> `work-units/BILL-WU-###.md`, and that spec is authoritative if this summary and it ever disagree.
> Status vocabulary: READY · READY WITH A TRACKED OPEN ITEM (abbreviated **READY-OI** in tables only) ·
> BLOCKED · OUT OF SCOPE. See `README.md` §Conventions.

## How the candidate workstreams were evaluated

The brief offered candidates A–K. The final structure differs where dependency logic required it:

- **Baseline repair was added in front of cardinality (WS-A, WP-A1).** The phantom `billing` entry in
  `INSTALLED_APPS` (BILL-RISK-01) probably stops the suite from running, and no other unit can be
  verified until it is fixed.
- **Cardinality was split into "author and test" (BILL-WU-006) and "apply to shared databases"
  (BILL-WU-007).** Only the second depends on the duplicate-owner data finding, so the gate doesn't
  stall code work.
- **"Billing module/persistence foundation" and "plan & entitlement" became three packages (B1, C1,
  C2).** The entitlement contract is a pure decision and is independent of where it is enforced;
  enforcement is split again by policy readiness. Plan-gated AI and student caps are decided (READY-OI).
  The general restricted-access ruleset is not (BLOCKED).
- **Failed-payment outcome recording (BILL-WU-029) is a foundation consumed by event processing and
  renewal**, not a late unit. Otherwise webhook FAILURE handling would have to be retrofitted. Moving it
  forward also removes an apparent cycle (see `dependency-graph.md` §Cycle check).
- **Renewal is split three ways:** capability (BILL-WU-025, READY-OI), production activation against a
  verified Kashier capability (BILL-WU-026, BLOCKED EXTERNAL), and the production scheduler
  (BILL-WU-027, BLOCKED OPERATIONAL). This is a true decomposition: the worker and charge logic can be
  built and verified against the fake provider, and only the production cadence depends on BILL-EXT-01.
- **Notifications are a BLOCKED unit of their own (BILL-WU-033).** The existing `Notification` model
  is student-recipient, five-event-catalog, TenantOwned, and its push provider is a no-op
  (`NullPushProvider`). Billing messages to teachers have no channel without a System-level catalog or
  channel decision (BILL-DEC-06).
- **A tracked OUT OF SCOPE workstream (K) was added** so policy-open features (refunds, proration,
  invoices/tax, AI quotas, price changes) are traceable rather than silently missing.

## Workstreams, packages, units

### BILL-WS-A — Baseline integrity & environment cardinality
*Package rationale:* A1 restores a verifiable baseline (precondition for all evidence). A2 holds every
INV-9 change: the read-only data check, the remediation gate, test realignment, migration authoring,
and the gated migration rollout share one data-integrity concern and one commit sequence.

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-A1 | BILL-WU-001 | Resolve phantom `billing` app registration; create the empty `billing` module skeleton | READY-OI (BILL-DEC-08) |
| BILL-WP-A1 | BILL-WU-002 | Establish and record the pre-change regression baseline (PostgreSQL test DB + full suite) | READY |
| BILL-WP-A2 | BILL-WU-003 | Pre-migration duplicate-owner data check (read-only) | READY |
| BILL-WP-A2 | BILL-WU-004 | Duplicate-owner remediation (conditional, approval-gated) | BLOCKED (DATA + BILL-DEC-01) |
| BILL-WP-A2 | BILL-WU-005 | Realign tests, fixtures and seed data with INV-9 | READY |
| BILL-WP-A2 | BILL-WU-006 | `Environment.owner` → OneToOneField: migration, DB uniqueness, regression tests | READY |
| BILL-WP-A2 | BILL-WU-007 | Apply the cardinality migration to shared databases (dev/staging/prod) | BLOCKED (DATA on 003/004) |

### BILL-WS-B — Billing module & persistence foundation
*Package rationale:* one package. Persistence and the plan catalog share a migration chain and the
same DAT-5 authority.

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-B1 | BILL-WU-008 | Billing persistence foundation (DAT-5 logical concepts, integrity constraints) | READY-OI (state names; invoice scope) |
| BILL-WP-B1 | BILL-WU-009 | Plan catalog and capability keys | READY-OI (BILL-DEC-07) |

### BILL-WS-C — Entitlement contract & enforcement
*Package rationale:* C1 is the provider-neutral decision (one owner: Billing). C2 holds the consumption
points, which touch other modules and have different policy readiness.

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-C1 | BILL-WU-010 | Entitlement-policy contract (Billing-owned capability) | READY-OI (BILL-DEC-02 surfaced as state, not behaviour) |
| BILL-WP-C2 | BILL-WU-011 | Entitlement enforcement integration (permission layer after tenant resolution; plan-gated AI on Web and Worker) | READY-OI (BILL-DEC-07) |
| BILL-WP-C2 | BILL-WU-012 | Student-cap enforcement (trial 250 / 400 / 800 / none) | READY-OI (count definition, BILL-DEC-07) |
| BILL-WP-C2 | BILL-WU-013 | Access-not-granted restriction ruleset (teacher read-only, student-facing, export path) | BLOCKED (BILL-DEC-02) |

### BILL-WS-D — Trial lifecycle & activation integration
*Package rationale:* everything that creates or constrains trial state at, or relative to, the signup
event.

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-D1 | BILL-WU-014 | Start the 16-day trial inside the atomic teacher-signup transaction | READY |
| BILL-WP-D1 | BILL-WU-015 | Commercial state for pre-existing teacher accounts (backfill) | BLOCKED (BILL-DEC-03) |
| BILL-WP-D1 | BILL-WU-016 | Repeat-trial / trial-abuse controls | BLOCKED (BILL-DEC-04) |

### BILL-WS-E — Provider contract & initial checkout
*Package rationale:* E1 is the ADR-015 trust boundary (interface, fake, Kashier adapter, secrets). E2 is
the first teacher-initiated money flow on top of it.

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-E1 | BILL-WU-017 | Payment-provider interface, fake provider, configuration and secrets | READY |
| BILL-WP-E1 | BILL-WU-018 | Kashier adapter (outbound: save-token session, pay-with-token, status lookup) | READY-OI (BILL-EXT-02/03) |
| BILL-WP-E2 | BILL-WU-019 | Checkout initiation, correlation, redirect handling | READY-OI (BILL-EXT-05; BILL-EXT-01 for agreement params) |

### BILL-WS-F — Inbound payment events & state integrity
*Package rationale:* F1 is the ingress (verification and durable receipt, the ADR-016 prerequisites).
F2 is application, recovery and reconciliation (the ADR-017 state separation). They are separate
because ingress must ack within Kashier's 30-second window while application may be retried.

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-F1 | BILL-WU-020 | Kashier webhook endpoint: signature verification, raw body, durable receipt, dedup | READY-OI (BILL-EXT-03) |
| BILL-WP-F2 | BILL-WU-021 | Event application: correlation, status semantics, transactional state transitions | READY-OI (BILL-EXT-03) |
| BILL-WP-F2 | BILL-WU-022 | Event-processing recovery worker (`process_billing_events`) | READY |
| BILL-WP-F2 | BILL-WU-023 | Reconciliation of ambiguous/pending/missed outcomes | READY-OI (BILL-EXT-03 status API) |

### BILL-WS-G — Recurring renewal
*Package rationale:* G1 is buildable and verifiable capability. G2 holds the two production gates
(external compatibility and operational scheduling), kept apart so neither silently blocks G1.

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-G1 | BILL-WU-024 | Billing-period computation (30 elapsed days, server-authoritative) | READY |
| BILL-WP-G1 | BILL-WU-025 | Renewal execution capability (`process_billing_renewals`, atomic claim, single attempt) | READY-OI (BILL-DEC-05 retries excluded; production disabled) |
| BILL-WP-G2 | BILL-WU-026 | Kashier 30-day compatibility gate and production renewal activation | BLOCKED (BILL-EXT-01) |
| BILL-WP-G2 | BILL-WU-027 | Production scheduler arrangement for billing worker commands | BLOCKED (BILL-OPS-01) |

### BILL-WS-H — Cancellation & payment-failure recovery

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-H1 | BILL-WU-028 | Cancel-at-period-end with renewal race safety | READY-OI (agreement-side cancellation, BILL-EXT-03) |
| BILL-WP-H1 | BILL-WU-029 | Failed-payment outcome recording foundation | READY-OI (BILL-DEC-05 numbers excluded) |
| BILL-WP-H1 | BILL-WU-030 | Retry schedule and grace-period execution | BLOCKED (BILL-DEC-05) |

### BILL-WS-I — API, Frontend hand-off, notifications
*Package rationale:* I1 is client-facing contract surface. I2 is outbound messaging, which is policy- and
catalog-blocked.

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-I1 | BILL-WU-031 | Teacher billing API namespace and read endpoints | READY-OI (NODE-WireAPI) |
| BILL-WP-I1 | BILL-WU-032 | Frontend contract hand-off | READY-OI (BILL-DEC-02 portions) |
| BILL-WP-I2 | BILL-WU-033 | Billing notifications to the teacher | BLOCKED (BILL-DEC-06) |

### BILL-WS-J — Testing, hardening, launch verification

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-J1 | BILL-WU-034 | Billing adversarial/security test suite | READY |
| BILL-WP-J1 | BILL-WU-035 | Billing observability, audit trail, log redaction | READY-OI (observability vendor fenced) |
| BILL-WP-J2 | BILL-WU-036 | Kashier sandbox end-to-end verification | BLOCKED (BILL-EXT-02) |
| BILL-WP-J2 | BILL-WU-037 | Staging verification, merchant go-live, production smoke | BLOCKED (BILL-EXT-04 + upstream gates) |

### BILL-WS-K — Tracked out-of-scope items

| WP | WU | Title | Status |
|---|---|---|---|
| BILL-WP-K1 | BILL-WU-038 | Refunds | OUT OF SCOPE |
| BILL-WP-K1 | BILL-WU-039 | Upgrade/downgrade timing and proration | OUT OF SCOPE |
| BILL-WP-K1 | BILL-WU-040 | Invoice/receipt/tax documents | OUT OF SCOPE |
| BILL-WP-K1 | BILL-WU-041 | AI usage quotas / cost controls | OUT OF SCOPE |
| BILL-WP-K1 | BILL-WU-042 | Price-change treatment for existing subscribers | OUT OF SCOPE |

## Totals (enumerated — see `plan-validation.md` §2 for the literal tally)

- Workstreams: **11** (A–K). Work Packages: **18** (A1, A2, B1, C1, C2, D1, E1, E2, F1, F2, G1, G2, H1,
  I1, I2, J1, J2, K1).
- Work Units: **42** = **9 READY** + **17 READY WITH A TRACKED OPEN ITEM** + **11 BLOCKED** + **5 OUT OF
  SCOPE**.
