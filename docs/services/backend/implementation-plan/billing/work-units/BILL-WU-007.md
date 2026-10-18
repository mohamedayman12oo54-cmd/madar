# BILL-WU-007 — Apply the cardinality migration to shared databases

**ID:** BILL-WU-007 · **Workstream/Package:** BILL-WS-A / BILL-WP-A2
**Status:** BLOCKED
**Blocked by:** DATA. BILL-WU-003 must report zero duplicates for the DB, or BILL-WU-004 must have remediated it under BILL-DEC-01. Also OPERATIONAL (deployment access, backup).
**Priority / Risk:** P0 / High

## Purpose
Roll the BILL-WU-006 migration out to each shared database (dev → staging → prod) only after that DB
is proven INV-9-compliant, so the DB-level guarantee holds wherever Billing will run.

## Expected outcome
Each target DB has `environments.0002_*` applied; BILL-WU-003 reports zero duplicates after the migration;
a uniqueness rejection is demonstrated in staging.

## Requirement / invariant references
INV-9; ADR-013.

## Relevant ADRs / contracts
ADR-013; `09-operations/deployment.md` (three environments).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-006 | BLOCKING | Yes | The migration must exist and be verified |
| BILL-WU-003 (per-DB report) | DATA | Yes | Must show zero duplicates |
| BILL-WU-004 | DATA | Yes, only if duplicates exist | Remediation first |
| Backup/PITR confirmed per DB | OPERATIONAL | Yes | Rollback path |

## Preconditions
Per DB: fresh BILL-WU-003 report (zero); backup confirmed; deploy window agreed.

## In-scope changes
Running `migrate` per environment as part of the normal deploy; capturing evidence.

## Explicit exclusions
Any data remediation (BILL-WU-004); prod before staging.

## Implementation surfaces (grounded at bf115df)
`apps/backend/environments/migrations/0002_*` (from BILL-WU-006); deployment mechanism (Operations,
not in repo: `infra/` is empty).

## Data-integrity & security considerations
Re-run BILL-WU-003 immediately before migrating, because data could change between check and migration.
The migration is transactional on PostgreSQL, so failure leaves the DB unchanged.

## Failure modes
Duplicate created between check and migrate (migration fails safely; re-check); deploy without backup
(prohibited).

## Acceptance criteria
- **AC-BILL-007-1:** For each DB, BILL-WU-003 output captured within the same deploy window shows zero duplicates before migrating.
- **AC-BILL-007-2:** `showmigrations environments` shows `0002_*` applied in dev, staging and prod.
- **AC-BILL-007-3:** In staging, an attempt to create a second Environment for an existing teacher (e.g., via shell in a disposable transaction) is rejected by the DB.

## Verification methods & required evidence
Ops record per DB: pre-check log, migrate log, `showmigrations` output, staging rejection log.

## Dependencies required before execution
BILL-WU-006 VERIFIED; per-DB BILL-WU-003 zero (or BILL-WU-004 done).

## Completion definition
AC-1..3 for all three environments. Production completion is a precondition of BILL-WU-037 (launch).

## Commit boundaries
None (deployment activity).

## Escalation conditions
Migration fails in any environment; any duplicate in production.
