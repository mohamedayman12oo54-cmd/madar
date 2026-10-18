# BILL-WU-001 — Resolve phantom `billing` app registration; create the empty `billing` module skeleton

**ID:** BILL-WU-001 · **Workstream/Package:** BILL-WS-A / BILL-WP-A1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** BILL-DEC-08 (confirm with the author of commit `6b876b4` whether an uncommitted `billing` implementation exists elsewhere)
**Priority / Risk:** P0 / High (gates every verification in this plan)

## Purpose
Make the Backend importable and bootable again. `apps/backend/config/settings.py:126` registers
`"billing"` in `INSTALLED_APPS`, but there is no `apps/backend/billing/` package (BILL-RISK-01). Create
the empty bounded-module skeleton that ADR-014 names, so the registration resolves to the real module
the rest of this plan builds on.

## Expected outcome
`apps/backend/billing/` exists as a Django app (`__init__.py`, `apps.py` with `name = "billing"`, an empty
`migrations/__init__.py`, and a module docstring stating ownership per ADR-014 and the distinction from
`financials`). It has **no models, no URLs, no views**. Django app loading succeeds.

## Requirement / invariant references
ADR-014 (module name `billing`, eighth module); BND-1/BND-4 (private persistence); BD-25.

## Relevant ADRs / contracts
ADR-001, ADR-012, ADR-014.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-DEC-08 (author confirmation re: uncommitted implementation) | DECISION | Non-blocking for execution; blocking for *merging* if a competing implementation exists | Avoid two diverging `billing` apps |
| BILL-OPS-02 (PostgreSQL available locally to prove boot) | ENVIRONMENT | Non-blocking for authoring; blocking for verification | `settings.py:173-176` refuses to load without DB credentials |

## Preconditions
Read `settings.py:100-127` and `:160-176`. Confirm the `billing` directory is still absent
(`git ls-files apps/backend/billing`).

## In-scope changes
Create the skeleton package. Leave the `settings.py` comment at `:167-169` alone unless it contradicts
the delivered design. If it does, record a deviation; don't rewrite it silently.

## Explicit exclusions
No models, migrations with operations, URLs, admin registrations, or settings changes. The alternative
fix (removing the `INSTALLED_APPS` entry) is **not** taken without BILL-DEC-08, because ADR-014 names
this module.

## Implementation surfaces (grounded at bf115df)
`apps/backend/config/settings.py:126` (existing entry); new `apps/backend/billing/{__init__.py,apps.py,migrations/__init__.py}`.
Pattern: any existing app's `apps.py` (e.g., `apps/backend/financials/apps.py`).

## Data-integrity & security considerations
None at runtime. An empty app adds no tables. Make sure no `billing` name shadows a third-party package
(an import-spec check found none).

## Failure modes
A competing uncommitted implementation lands later and conflicts (mitigated by BILL-DEC-08); the app
label collides with a future dependency (low).

## Acceptance criteria
- **AC-BILL-001-1:** `python manage.py check` completes with no `ModuleNotFoundError` for `billing`.
- **AC-BILL-001-2:** `apps/backend/billing/` contains no model classes; `makemigrations billing --check --dry-run` reports no changes.
- **AC-BILL-001-3:** BILL-DEC-08's outcome is recorded in the PR description (confirmed "no other implementation", or a link to it).

## Verification methods & required evidence
Command output of `manage.py check` and `makemigrations --check` (ENVIRONMENT: Postgres creds set); PR record for AC-3.

## Dependencies required before execution
None. This is the root unit.

## Completion definition
AC-1..3 met with evidence attached; status VERIFIED.

## Commit boundaries
One commit: `feat(billing): add empty billing app skeleton registered in settings`.

## Escalation conditions
BILL-DEC-08 reveals an existing implementation, or the team decides to remove the registration instead.
Either case changes ADR-014's realization: stop and escalate.
