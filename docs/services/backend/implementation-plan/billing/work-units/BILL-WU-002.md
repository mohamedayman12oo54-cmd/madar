# BILL-WU-002 — Establish and record the pre-change regression baseline

**ID:** BILL-WU-002 · **Workstream/Package:** BILL-WS-A / BILL-WP-A1
**Status:** READY
**Priority / Risk:** P0 / Medium

## Purpose
Prove the existing suite runs green at the starting commit (plus BILL-WU-001) before any billing or
cardinality change, so every later regression is attributable. No CI exists (`.github/` holds only
`.gitkeep`), so this baseline is the only regression reference.

## Expected outcome
A recorded run of `python manage.py test` against PostgreSQL, giving the commit SHA, test count,
pass/fail/error counts, duration and DB version, attached to the PR or work log. Any pre-existing
failure is listed and triaged as "pre-existing", not fixed inside this plan unless it blocks billing work.

## Requirement / invariant references
Implemented ≠ Verified principle (`../verification.md`); all INV-1..9 regression coverage.

## Relevant ADRs / contracts
OP-PARITY (guarantees are equal across environments); `apps/backend/POSTGRESQL.md`.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-001 | BLOCKING | Yes | Suite likely can't load apps without it |
| BILL-OPS-02 (local/CI PostgreSQL) | ENVIRONMENT | Yes | Settings require Postgres credentials; tests need a DB |

## Preconditions
`docker compose up -d db` (`apps/backend/docker-compose.yml`) or equivalent; `.env` with DB vars.

## In-scope changes
None to code. Produce evidence only.

## Explicit exclusions
Introducing CI (recommended, not in scope; see BILL-RISK-10). Fixing unrelated pre-existing failures.

## Implementation surfaces (grounded at bf115df)
`apps/backend/manage.py`, `apps/backend/docker-compose.yml`, `apps/backend/.env.example:41-48`.

## Data-integrity & security considerations
Use a throwaway DB; never point the test run at a shared database.

## Failure modes
Pre-existing failures unrelated to billing (record them); environment drift (record the Postgres version).

## Acceptance criteria
- **AC-BILL-002-1:** The full suite has been executed and the result recorded with SHA, counts and Postgres version.
- **AC-BILL-002-2:** Every failing or erroring test (if any) is listed with a one-line triage note.

## Verification methods & required evidence
Captured test-runner output (text log) linked from the work log.

## Dependencies required before execution
BILL-WU-001.

## Completion definition
Baseline evidence exists and is referenced by BILL-WU-005/006 as their "before" state.

## Commit boundaries
None (evidence only). If a log is kept in-repo, use `test(billing): record pre-change regression baseline`. Prefer the PR description.

## Escalation conditions
The suite cannot be run at all for reasons other than BILL-RISK-01, or many failures suggest the
baseline is unsound.
