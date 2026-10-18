# BILL-WU-003 — Pre-migration duplicate-owner data check (read-only)

**ID:** BILL-WU-003 · **Workstream/Package:** BILL-WS-A / BILL-WP-A2
**Status:** READY
**Priority / Risk:** P0 / High (its output decides whether BILL-WU-004 is needed and whether BILL-WU-007 may proceed)

## Purpose
Before any database receives a uniqueness constraint on `Environment.owner`, determine factually
whether it already holds Teacher Accounts that own more than one Environment. ADR-013 §Consequences
states no live database has been checked. BILL-RISK-03 shows `seed_demo.py:39-46` creates two
Environments for one teacher, so any seeded dev/staging DB **will** fail the migration.

## Expected outcome
A **read-only** check: a management command `check_environment_cardinality` in the `environments` app,
or an equivalent reviewed SQL query kept with the plan evidence. For each target database it reports:
count of owners with >1 Environment; for each such owner, the user id, the Environment ids, each
Environment's `created_at`, and a per-Environment volume summary (count of Enrollments, Grades,
MonthlyPayments, AIOperations, Notifications, ContentItems). It also reports **owner-membership
coherence**: Environments whose `owner` lacks an `EnvironmentMembership(role=owner)`, and owner
memberships pointing at Environments the user doesn't own (BILL-RISK-27). The check must **never
write**.

Design (logical): `SELECT owner_id, COUNT(*) FROM environments_environment GROUP BY owner_id HAVING COUNT(*) > 1`,
followed by per-environment counts through each owning module's tables. Ownership counts are read-only
diagnostics, an accepted exception to BND-1 for an operator tool. Exit code: non-zero when any
duplicate exists, so it can gate BILL-WU-007.

## Requirement / invariant references
INV-9; ADR-013 §Consequences ("checking any live database for pre-existing violating data"); TAL-2 implementation follow-up.

## Relevant ADRs / contracts
ADR-013; DAT-4.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-001 | BLOCKING | Yes | App must boot to run a management command |
| Read access to each target DB (dev, staging, prod) | OPERATIONAL | Blocking for *running* against that DB | Operations grants read-only access |

## Preconditions
Agreed list of target databases (BILL-OPS-03 inventory: which dev/staging/prod DBs exist).

## In-scope changes
The read-only command plus its unit tests (fixture with 0, 1, and 2 environments per owner; incoherent membership).

## Explicit exclusions
Any deletion, merge, re-parenting or update. Remediation is BILL-WU-004 and needs approval.

## Implementation surfaces (grounded at bf115df)
New `apps/backend/environments/management/commands/check_environment_cardinality.py` (the `environments`
app has no `management/` package yet). Models: `environments/models.py:14-66`. Pattern for command
structure: `ai/management/commands/process_ai_operations.py:46-63`.

## Data-integrity & security considerations
Output contains user ids and environment ids only. **No names, phones or emails** in the report
(minors' data posture, `security-authz.md`). Run with a read-only DB role where available.

## Failure modes
Long-running counts on large tables (bounded: group-by on a small table, then per-duplicate drill-down
only); being run against the wrong DB (the report prints DB name/host).

## Acceptance criteria
- **AC-BILL-003-1:** Against a fixture DB with one owner owning two Environments, the command reports exactly that owner and both ids, and exits non-zero.
- **AC-BILL-003-2:** Against a fixture DB where every owner has exactly one Environment, it reports zero and exits zero.
- **AC-BILL-003-3:** It reports owner/membership incoherence cases.
- **AC-BILL-003-4:** A test asserts the command performs no writes (e.g., wrap in `assertNumQueries` with only SELECTs, or run inside a transaction and compare row counts).
- **AC-BILL-003-5:** The report contains no PII fields (test asserts absence of name/phone/email).
- **AC-BILL-003-6 (operational):** The command's report has been captured for **each** target DB and attached to BILL-WU-004 / BILL-WU-007 evidence.

## Verification methods & required evidence
Unit/integration tests (AC-1..5) in the suite; operational run logs per DB (AC-6).

## Dependencies required before execution
BILL-WU-001.

## Completion definition
Code AC-1..5 VERIFIED; AC-6 captured per DB. AC-6 can complete later than the code and gates BILL-WU-007, not BILL-WU-006.

## Commit boundaries
`feat(environments): add read-only environment cardinality check command`, then `test(environments): cover environment cardinality check`.

## Escalation conditions
Any duplicate found in **production**, or owner-membership incoherence found anywhere. Both route to BILL-DEC-01.
