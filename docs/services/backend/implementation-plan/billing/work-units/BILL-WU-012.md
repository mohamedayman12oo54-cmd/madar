# BILL-WU-012 — Student-cap enforcement (trial 250 / Plan 1 400 / Plan 2 800 / Plan 3 none)

**ID:** BILL-WU-012 · **Workstream/Package:** BILL-WS-C / BILL-WP-C2
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** "student" count definition (BILL-DEC-07 sub-item). Candidates: active Enrollments in the
Environment's current Academic Year; all active Enrollments; or student memberships. The cap numbers
are decided; the counted set is not stated in commercial-model. Behaviour when an existing roster
already exceeds a new cap (e.g., trial expiry to Plan 1 with 300 students) depends on downgrade policy,
which is OUT OF SCOPE (BILL-WU-039). This unit blocks **only new additions** and never removes or
deactivates students.
**Priority / Risk:** P1 / Medium (race condition risk)

## Purpose
Backend-enforce the decided student caps when a teacher adds or re-activates a student.

## Expected outcome
Enrollment creation (`EnrollmentListCreateView.post`, `apps/backend/academics/views.py:132-147`, via
`EnrollmentCreateSerializer`) and re-activation (`EnrollmentDetailView`, `academics/views.py:150+`, when
`is_active` flips to True) consult `billing.entitlements.decide(request.environment).student_cap`. If
the counted set is already ≥ cap, the request is rejected with a stable code (e.g., `student_cap_reached`).
The count and insert are race-safe: lock the Environment's Subscription row (`select_for_update`) inside
the same `transaction.atomic()` as the insert, so two concurrent adds cannot both pass at cap − 1.

## Requirement / invariant references
commercial-model §Plans (caps), §Free trial (250); functional §Billing; AL-4 (student-count-limit responses); BND-1 (count obtained via an academics capability, not by billing reading academics tables).

## Relevant ADRs / contracts
ADR-018; BND-1/BND-4.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-010 | CONTRACT | Yes | Cap source |
| BILL-WU-009 | DATA | Yes | Cap values |
| BILL-DEC-07 (count definition) | DECISION | Non-blocking: implement behind one function `count_for_cap(environment)` owned by academics; definition recorded as open | Avoid scattering the rule |

## Preconditions
Read `academics/serializers.py` `EnrollmentCreateSerializer` and `academics/views.py:101-200`.

## In-scope changes
Academics-owned counting capability; guard in create and re-activate paths; billing exception; tests including a concurrency test.

## Explicit exclusions
Deactivating or removing students over cap; downgrade handling; student-facing messaging; any count
inside `financials`.

## Implementation surfaces (grounded at bf115df)
`apps/backend/academics/views.py:101-147,150+`; `apps/backend/academics/serializers.py`; `apps/backend/billing/entitlements.py`.

## Data-integrity & security considerations
Lock order: Subscription row, then insert, consistent with BILL-WU-021/028 (documented single lock order
"Subscription row first"). A Plan 3 environment has no cap and takes no lock contention beyond the read.

## Failure modes
Race allowing cap + 1 (mitigated by lock, tested with two threads/transactions on Postgres); idempotent
re-enroll of an existing student (`created=False` path at `views.py:137`) must not be counted as an addition.

## Acceptance criteria
- **AC-BILL-012-1:** A trial environment with 250 counted students rejects the 251st add with `student_cap_reached`; Plan 1 at 400; Plan 2 at 800; Plan 3 accepts beyond 800.
- **AC-BILL-012-2:** Re-activating an inactive enrollment at cap is rejected; deactivating is always allowed.
- **AC-BILL-012-3:** Two concurrent adds at cap − 1 result in exactly one success (PostgreSQL concurrency test).
- **AC-BILL-012-4:** Existing over-cap rosters are untouched (no deactivation occurs).
- **AC-BILL-012-5:** The count definition used is a single function with a docstring referencing the open item.

## Verification methods & required evidence
Integration tests (TenantTestCase); concurrency test (`TransactionTestCase`); review.

## Dependencies required before execution
BILL-WU-010.

## Completion definition
AC-1..5 VERIFIED; count definition open item tracked.

## Commit boundaries
`feat(academics): enforce billing student cap on enrollment`; `test(academics): cover student cap and concurrent enrollment`.

## Escalation conditions
Any requirement to act on existing over-cap rosters; disagreement on what counts as a student.
