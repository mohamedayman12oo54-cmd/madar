# BILL-WU-006 — `Environment.owner` → OneToOneField: migration, DB uniqueness, regression tests

**ID:** BILL-WU-006 · **Workstream/Package:** BILL-WS-A / BILL-WP-A2
**Status:** READY
**Priority / Risk:** P0 / High (schema change on the tenant root)

## Purpose
Enforce INV-9 structurally in the ORM and in PostgreSQL, as ADR-013 §Consequences requires: "`OneToOneField`
is the expected semantic target for `Environment.owner`, replacing the current `ForeignKey`."

## Expected outcome
`Environment.owner` is a `OneToOneField` (keeping `on_delete=CASCADE` and `limit_choices_to={"role": "teacher"}`).
A new migration `environments/0002_*` changes the field, which yields a unique index on `owner_id` in
PostgreSQL. The model docstring stops saying "A teacher may own several." Regression tests prove a second
Environment for the same owner is rejected and signup still creates exactly one. **This unit authors and
tests the migration on clean test databases only.** Applying it to shared databases is BILL-WU-007.

## Requirement / invariant references
INV-9; ADR-013; TAL-2; DAT-4; BD-22.

## Relevant ADRs / contracts
ADR-013 (reconciles with ADR-008 without editing it); `07-contracts/api-contract.md` (list endpoint shape unchanged).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-005 | BLOCKING | Yes | Otherwise the existing suite violates the new constraint |
| BILL-WU-001 | BLOCKING | Yes | Suite must boot |
| BILL-WU-003 code | Non-blocking | No | Rollout uses it; authoring doesn't |

## Preconditions
Re-read `environments/models.py:14-40` and `migrations/0001_initial.py:17-31` (the only migration).

## In-scope changes
1. `environments/models.py:19-22`: `models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name=<decide>, limit_choices_to={"role": "teacher"})`.
2. **Reverse-relation semantics change.** With a ForeignKey, `user.owned_environments` is a manager
   (queryset). With a OneToOneField it becomes a single object that raises `RelatedObjectDoesNotExist`
   when absent. A grep at `bf115df` found **no** code using the `owned_environments` accessor (only its
   definition at `models.py:20`), and all call sites use `Environment.objects.filter(owner=...)`
   (`environments/views.py:25`, `accounts/tests.py:93`, `test_phase1_tenancy.py:149`), which still works.
   Choose the `related_name` deliberately (e.g., `owned_environment`). Renaming changes the reverse
   accessor only, not a DB column. Re-grep before merging.
3. Update the docstring (`models.py:15-17`) to reference INV-9/ADR-013.
4. Generate the migration with `makemigrations environments`. Review that it is an `AlterField` producing
   a unique constraint/index. Name it descriptively.
5. Keep `TeacherEnvironmentListView` (`environments/views.py:21-27`) returning a **list**. That is the
   Frontend contract. It will contain ≤ 1 item.
6. `TeacherEnvironmentEnterView` (`views.py:30-41`) needs no change.
7. `TeacherSignupEnvironmentView` (`accounts/views.py:157-200`) already catches `IntegrityError` (`:192`).
   A new user can't collide on `owner_id`, so the 409 path is not newly reachable. Verify by test.

## Explicit exclusions
Running this migration on any shared DB (BILL-WU-007). Changing ADR-008 context resolution. Changing
`EnvironmentMembership` constraints. Adding an owner-membership uniqueness rule is **not** decided by
INV-9; record it as BILL-RISK-27 rather than adding it here.

## Implementation surfaces (grounded at bf115df)
`apps/backend/environments/models.py:14-40`; new `apps/backend/environments/migrations/0002_*.py`;
`apps/backend/environments/tests.py` (new tests); `apps/backend/accounts/tests.py:85-100` (existing
signup assertion `Environment.objects.filter(owner=user).count() == 1`, kept).

## Data-integrity & security considerations
The migration **fails** on any DB with duplicate owners (PostgreSQL can't build the unique index). That
is intended, but it means BILL-WU-007 must not run before BILL-WU-003/004 clear the DB. Migration
reversibility: the reverse `AlterField` back to ForeignKey must be generated and tested. Lock impact:
building a unique index on a small table is brief, but note it for prod.

## Failure modes
Duplicate data in a target DB (migration aborts, transactional on Postgres); a hidden reverse-accessor
usage breaks at runtime (mitigated by grep plus full suite); Frontend assumes a multi-item list (no
behavioural change, list shape kept).

## Acceptance criteria
- **AC-BILL-006-1:** `Environment.owner` is a OneToOneField; `makemigrations --check` is clean after the new migration.
- **AC-BILL-006-2:** A test creating a second `Environment` for the same owner raises `IntegrityError` at the DB level (not just a model `clean()`).
- **AC-BILL-006-3:** The existing signup test (`accounts/tests.py:85-100`) still passes: exactly one Environment and one owner membership.
- **AC-BILL-006-4:** `GET /api/v1/environments/teacher/` still returns a JSON list (length 1 for a teacher with one environment).
- **AC-BILL-006-5:** The migration applies forward and reverses cleanly on an empty test DB (`migrate environments 0001` then `migrate`).
- **AC-BILL-006-6:** The full suite passes on the new schema.
- **AC-BILL-006-7:** On a test DB pre-loaded with a duplicate owner, applying the migration fails, proving the gate is real. This can be a documented manual rehearsal if not automatable.

## Verification methods & required evidence
Unit/integration tests (AC-2..4, 6); migration rehearsal log (AC-5, 7); diff review of the generated migration.

## Dependencies required before execution
BILL-WU-001, BILL-WU-005.

## Completion definition
AC-1..7 VERIFIED. The unit is complete **without** any shared DB being migrated.

## Commit boundaries
`feat(environments): enforce one environment per teacher with OneToOneField` (model + migration together);
`test(environments): cover one-environment-per-teacher constraint`.

## Escalation conditions
Any code path found that needs multiple environments per teacher; any requirement to add owner-membership
uniqueness; any change to ADR-008 behaviour.
