# Madar Backend — Billing / Kashier Implementation Plan (BILL-PLAN-01)

> **Plan ID:** BILL-PLAN-01 · **Title:** Billing module, Teacher trial/subscription lifecycle, and Kashier
> payment-provider integration — Backend Implementation Plan
> **Status:** **DRAFT** — not READY. Authored documents exist; that alone does not make the plan
> executable end-to-end (see `plan-validation.md`).
> **Authority:** Layer 4 (derived), same position as the Backend-wide plan in `../README.md`:
> System Docs → Backend Service Docs → ADRs (ADR-001..018) → **this plan** → Engineering Skills → AI
> execution guidance → agent inference. This plan never overrides Documentation; where it needs system
> truth to change, it escalates (see `ai-execution-guidance.md`).
> **Nature:** planning artifact only. No application code, migrations, tests, or configuration were
> written, run, or changed while authoring it. **No tests were executed during plan authoring.**

## Baseline

| Item | Value |
|---|---|
| Branch | `update/databaseForPayment` |
| Commit | `bf115dffe861b581d8e2fe83e8d0aef4daba9e06` (`docs(billing): record Kashier commercial and architectural decisions`) |
| Working tree at authoring | clean except two pre-existing untracked root files (`KASHIER_BACKEND_READINESS_AUDIT.md`, `KASHIER_SUPPLEMENTARY_AUDIT.md`), untouched by this plan |
| Authoring date | 2026-10-15 |
| `apps/backend/` vs audits | unchanged since the audits, but **two facts the audits did not report** were found by re-reading the code (see "Baseline drift" below) |

### Documentation baseline (authoritative inputs)

- `docs/01-product/commercial-model.md` (normative commercial rules, open-items table)
- `docs/01-product/access-lifecycle.md`, `docs/02-requirements/functional.md` §Billing
- `docs/03-domain/invariants.md` (INV-9), `docs/03-domain/actor-lifecycles.md`
- `docs/04-architecture/architecture.md`, `docs/04-architecture/building-blocks.md`
- `docs/06-data/data-model.md` §Billing logical concepts; `docs/services/backend/06-data/data-model.md` DAT-4/DAT-5
- `docs/07-contracts/external-interfaces.md` (fourth interface + negative space), `docs/07-contracts/api-contract.md`
- ADR-013 (cardinality), ADR-014 (billing module), ADR-015 (provider interface), ADR-016 (narrow inbound
  webhook exception), ADR-017 (payment-event integrity), ADR-018 (entitlement boundary). Checked: there is
  no ADR-019+ and none of ADR-013..018 is amended or superseded, so all six stand as written.
- Backend specializations: `services/backend/01-scope/teacher-access-lifecycle.md` (TAL-2, TAL-5),
  `03-internal-boundaries/module-boundaries.md` (BND-1..4), `07-contracts/external-api-alignment.md`
  (AL-2..4), `08-cross-cutting/security-authz.md`, `09-operations/operations.md` (OP-PARITY),
  `10-decisions/decision-register.md` (BD-22..30), `11-validation/open-items.md`
- Evidence base (not authoritative): the two root audit files.
- External context (not authoritative, reviewed 2026-10-15): Kashier developer docs
  `developers.kashier.io/docs/accept-payments/recurring`, `/docs/webhooks`, `/docs/webhooks/payloads`,
  `/docs/get-started/going-live`. These inform the planning only. **They do not resolve the 30-day
  compatibility gate** (BILL-EXT-01).

### Baseline drift found during authoring (recorded, not fixed)

1. **A `billing` app is registered but doesn't exist (BILL-RISK-01, critical).** `apps/backend/config/settings.py:126`
   lists `"billing"` in `INSTALLED_APPS`, and `settings.py:167-169` has a comment describing billing
   design ("student-capacity limits, one invoice per cycle, webhook idempotency"). But there is no
   `apps/backend/billing/` package on this branch, `origin/main` or `origin/mostafa-frontend`, and no
   importable `billing` module in the local Python environment (an import-spec lookup returned `None`;
   nothing was executed). The entry came from commit `6b876b4` (2026-10-14). The supplementary audit (§3)
   reviewed that commit's settings diff and reported no billing or payment strings, so it missed this
   entry. Static inference: Django app loading at HEAD would fail with `ModuleNotFoundError`, so
   `manage.py test`, `migrate` and `runserver` probably cannot run at all right now. This was **not
   executed**, so it is unconfirmed.
2. **Seed data already breaks INV-9 (BILL-RISK-03).** `apps/backend/accounts/management/commands/seed_demo.py:39-46`
   creates **two** Environments for the same demo teacher. Any database that ran `seed_demo` already
   contains a duplicate owner. The supplementary audit (§18) listed seed data as unchecked.
3. Minor: the brief referenced `docs/11-validation/open-items.md`, which does not exist. The system-level
   validation folder has only `consistency-audit.md` and `traceability.md`. The backend file
   `docs/services/backend/11-validation/open-items.md` was used instead (BILL-RISK-25).

## Purpose and scope (summary — detail in `scope.md`)

Plan the Backend work that turns the decided commercial model and ADR-013..018 into verified behaviour:
enforce INV-9 at the database level; create the `billing` bounded module and its private persistence
(DAT-5); a Billing-owned entitlement contract enforced after tenant and authorization context is
resolved (ADR-018); trial start inside the existing atomic signup transaction; a Madar-owned
payment-provider interface with a Kashier adapter (ADR-015); checkout; the single approved inbound
webhook with signature verification, correlation and dedup (ADR-016/017); reconciliation; 30-day
renewal mechanics; cancel-at-period-end; recording of failed-payment outcomes; and the API, testing
and launch verification around all of it.

## Explicitly out of scope

Frontend/UI implementation (only contract hand-off is planned); refunds; upgrade/downgrade and
proration; invoice, receipt and tax documents; AI usage quotas and cost controls; price-change
treatment for existing subscribers; any inbound integration other than the Kashier payment-result
webhook; any change to `financials` (student fee tracking); any new broker or queue technology;
selecting a scheduler or hosting vendor; inventing any commercial number that is still open (retry
count/schedule, grace duration, repeat-trial rules, proration, refund policy). The out-of-scope items
that are tracked appear as OUT OF SCOPE Work Units BILL-WU-038..042.

## Planning assumptions and limits

- The ADRs and the commercial model are taken as accepted and binding. Open items stay open; no unit
  defaults them.
- Physical schema (field names, tables, indexes) is **not** mandated here unless DAT-5 or INV-9 already
  settles it. Units name logical concepts and the integrity guarantees they must provide.
- Kashier facts quoted here come from public docs reviewed on 2026-10-15. Each one stays an external
  fact to confirm in sandbox. None is treated as a contract.
- Code citations are to the files as they are at `bf115df`. An implementer must re-confirm line numbers
  before editing.
- The status vocabulary differs from the Backend-wide plan (see below), as the authoring brief
  required.

## Conventions (and deviations from `../`)

| Element | Backend-wide plan | This plan | Why |
|---|---|---|---|
| Workstream | `WS-FND` | `BILL-WS-A` … `BILL-WS-K` | Separate namespace so it can't collide with the 49 existing WUs |
| Work package | — (none) | `BILL-WP-A1` … | The authoring brief requires a WS→WP→WU hierarchy |
| Work unit | `FND-01` | `BILL-WU-001` … `BILL-WU-042` | Three digits; stable IDs |
| Acceptance criterion | AC-seed (unnumbered) | `AC-BILL-###-n` | Stable, traceable IDs |
| Status | READY · SEAM-READY · SPIKE · BLOCKED | **READY** · **READY WITH A TRACKED OPEN ITEM** · **BLOCKED** · **OUT OF SCOPE** | Required by the brief. Rough mapping: SEAM-READY ≈ READY WITH A TRACKED OPEN ITEM. No SPIKE is used; investigation lives inside units such as BILL-WU-003 and BILL-WU-036 |
| Dependency types | BLOCK/CONTRACT/DATA/ENV/DECISION/EXTERNAL/VERIF | BLOCKING/DECISION/CONTRACT/DATA/ENVIRONMENT/EXTERNAL/OPERATIONAL/VERIFICATION | Required by the brief (adds OPERATIONAL) |
| Gate/decision nodes | `NODE-*` | `BILL-DEC-*` (decision), `BILL-EXT-*` (external), `BILL-OPS-*` (operational) | Same role as the existing Nodes; these are not WUs |

**Status semantics.** **READY** means no unresolved decision, external fact or operational
prerequisite stands in the way of finishing and verifying the unit; ordinary predecessor units may
still have to finish first. **READY WITH A TRACKED OPEN ITEM** means the unit can be built and verified
now, but a named open item must stay explicitly unresolved inside it (behind a seam, flag or
configuration) and must not be defaulted. **BLOCKED** means the unit's boundary or completion depends on
an unresolved decision, external fact, or data or operational condition. **OUT OF SCOPE** means the unit
is tracked so it isn't lost, and is not planned for execution.

## Entry conditions (to begin executing this plan)

1. BILL-RISK-01 is resolved: either the `billing` app skeleton exists (BILL-WU-001) or the owner of
   commit `6b876b4` has confirmed the intent (BILL-DEC-08).
2. A PostgreSQL test database is available (`settings.py` refuses to load without
   `DB_USER/DB_PASSWORD/DB_HOST`; see `docker-compose.yml`). This is BILL-OPS-02.
3. The existing test suite has run green and the result is recorded (BILL-WU-002). This is the regression
   baseline.

## Exit conditions (plan complete)

All READY and READY WITH A TRACKED OPEN ITEM units are VERIFIED with evidence (`verification-plan.md`);
every BLOCKED unit is either unblocked and VERIFIED, or carried forward with a named owner and an
explicit launch decision; BILL-WU-037 (go-live smoke) has passed; no open item has been silently
defaulted. Until then the plan stays **DRAFT** or **IN EXECUTION**, never READY.

## Artifact index

| File | Purpose |
|---|---|
| `README.md` | This control document |
| `scope.md` | In/out of scope, reuse vs build vs modify, integration boundaries, dependencies, hand-offs |
| `work-breakdown.md` | Workstreams → Work Packages → Work Units, package rationale, status table |
| `work-units/BILL-WU-001.md` … `work-units/BILL-WU-042.md` | One file per Work Unit (42 files) |
| `dependency-graph.md` | Typed edges, Mermaid graph, cycle check, critical path, execution order |
| `verification-plan.md` | Test levels, AC linkage, fixtures, sandbox/staging/production verification, evidence rules |
| `traceability-matrix.md` | Requirement/ADR/risk → WU → AC → evidence, with orphan and gap flags |
| `risks-and-open-issues.md` | Risks, decisions, external and operational gates |
| `ai-execution-guidance.md` | Directives for a future Claude Code implementation session |
| `plan-validation.md` | Acceptance-criteria checklist, status counts, critical path, overall status |
