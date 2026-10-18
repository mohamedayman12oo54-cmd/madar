# BILL-WU-005 — Realign tests, fixtures and seed data with INV-9

**ID:** BILL-WU-005 · **Workstream/Package:** BILL-WS-A / BILL-WP-A2
**Status:** READY
**Priority / Risk:** P0 / Medium

## Purpose
Remove every place in tests, fixtures and seed data that creates more than one Environment for the
same teacher, so the uniqueness constraint (BILL-WU-006) doesn't break the suite and seeded DBs stop
producing INV-9 violations.

## Expected outcome
All Environment creation in tests and seeds uses one teacher per Environment. Test intent is preserved:
`test_lists_only_own_environments` still proves "a teacher sees only their own environment(s)", now with
one own environment plus another teacher's. The pagination test still exercises 25 rows.

## Requirement / invariant references
INV-9; ADR-013 §Consequences ("updating `environments/tests.py`'s existing multi-environment fixture").

## Relevant ADRs / contracts
ADR-013.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-002 | VERIFICATION | Yes | Need a green "before" state |

## Preconditions
Re-run the grep `Environment.objects.create|bulk_create|Environment(owner` under `apps/backend` (14 hits at `bf115df`).

## In-scope changes (at bf115df)
1. `apps/backend/environments/tests.py:26-31`: `env2` currently has `owner=self.teacher`. Remove `env2`
   or give it a third teacher. Update `test_lists_only_own_environments` (`:36-40`) to expect exactly
   `{"الصف الثالث"}`, and add an assertion that `other_env` is absent.
2. `apps/backend/environments/test_phase1_tenancy.py:139-150` (`StandardPaginationTests`) bulk-creates
   25 Environments for **one** teacher (`:148`). Create 25 teachers with one Environment each, **or**
   paginate a different queryset. The test is about pagination, not environments.
3. `apps/backend/accounts/management/commands/seed_demo.py:39-46` creates two Environments plus two
   owner memberships for the demo teacher. Use a second demo teacher for `env_b`, or drop `env_b`.
   Update `apps/backend/README.md` demo-credentials text if it references two environments.
4. Re-check the other creation sites (`academics/test_enrollment.py:34`, `accounts/testing.py:32`,
   `accounts/tests.py:189`, `accounts/test_otp_hardening.py:181`, `environments/tenancy_testing.py:36`,
   `environments/test_phase0_security.py:31`, `knowledge/tests.py:80`, `environments/tests.py:69`). They
   appear to use a fresh teacher per Environment. Confirm each call site doesn't reuse an owner across
   calls within one test.

## Explicit exclusions
Changing the model (BILL-WU-006). Changing the list endpoint's response shape
(`environments/views.py:21-27` stays a list, which is a Frontend contract).

## Implementation surfaces (grounded at bf115df)
Listed above.

## Data-integrity & security considerations
Seed data must not reintroduce duplicates in any environment it's run against.

## Failure modes
A hidden helper reuses an owner (caught by BILL-WU-006's constraint in CI or local runs); a test loses
its original intent (review needed).

## Acceptance criteria
- **AC-BILL-005-1:** No test or seed code path creates two Environments with the same owner (grep plus review, and proven by BILL-WU-006's constraint passing the full suite).
- **AC-BILL-005-2:** `test_lists_only_own_environments` asserts the own environment is listed and the other teacher's is not.
- **AC-BILL-005-3:** The pagination test still asserts multi-page behaviour over ≥ 21 rows.
- **AC-BILL-005-4:** Running `seed_demo` twice on an empty DB leaves every teacher with exactly one Environment (BILL-WU-003 check returns zero).

## Verification methods & required evidence
Full-suite run on the pre-constraint schema (must stay green); BILL-WU-003 command output after `seed_demo`.

## Dependencies required before execution
BILL-WU-002.

## Completion definition
AC-1..4 VERIFIED; suite green.

## Commit boundaries
`test(environments): align environment fixtures with one-environment-per-teacher`; `fix(accounts): seed demo data with one environment per teacher`.

## Escalation conditions
A test whose purpose genuinely requires multi-environment ownership. That would contradict INV-9, so
escalate rather than delete the coverage.
