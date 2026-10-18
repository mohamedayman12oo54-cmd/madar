# BILL-WU-013 — Access-not-granted restriction ruleset (teacher read-only, student-facing behaviour, export path)

**ID:** BILL-WU-013 · **Workstream/Package:** BILL-WS-C / BILL-WP-C2
**Status:** BLOCKED
**Blocked by:** DECISION BILL-DEC-02. commercial-model §Open items lists "Student-facing restricted-access
behavior (exact rules)" and "Teacher-facing read-only permission ruleset post-expiry (exact
endpoints/scope)" as Open; NODE-AccessBehavior in `../decisions.md`.
**Priority / Risk:** P0 for launch / High

## Purpose
Once BILL-DEC-02 decides it, apply the restriction of **general** (non-plan-gated) educational
capability when access is not granted. Today an expired-trial teacher without a subscription would keep
full non-AI functionality, so this unit is a **launch prerequisite** (BILL-WU-037).

## Expected outcome (shape only; rules come from BILL-DEC-02)
A declarative ruleset (which endpoint categories are write-blocked or read-only for teacher and student
actors when `access_granted=False`), applied through the same permission mechanism as BILL-WU-011,
after tenant resolution. A **data review/export path** must exist in the not-granted state
(commercial-model §Access-not-granted). **Gap:** no export capability exists in the codebase today (a
grep for export/CSV found none outside unrelated files), so delivering it may be new work. See
`traceability-matrix.md` gap G-01.

## Requirement / invariant references
commercial-model §Access-not-granted principle; functional §Billing bullet 5; ADR-018; TAL-5; lifecycle-retention (no deletion).

## Relevant ADRs / contracts
ADR-018, ADR-010, AL-2.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-DEC-02 | DECISION | Yes | Rules undecided |
| BILL-WU-011 | BLOCKING | Yes | Reuses the enforcement mechanism |
| (coordination) Frontend contract update | — | Non-blocking, not a graph edge | When BILL-DEC-02 lands, the "pending" restricted-state section of BILL-WU-032's hand-off is completed as part of this unit's PR |

## Preconditions
BILL-DEC-02 recorded in `docs/01-product/commercial-model.md` (or successor) by its owner. **Not by this plan.**

## In-scope changes
To be specified after BILL-DEC-02. Expected: a ruleset module, decorators on affected views, export endpoint(s) if decided, and tests.

## Explicit exclusions
Inventing any rule in advance; deleting or hiding data; any change to authentication.

## Implementation surfaces (grounded at bf115df)
Expected: all teacher views using `IS_ENV_OWNER` (e.g., `academics/views.py:24`, `scheduling/views.py:27`,
`content/views.py:15`, `evaluation/views.py:26`, `financials/views.py:18`, `notifications/views.py:16`);
`studentarea/views.py:55-56`; `billing/permissions.py`.

## Data-integrity & security considerations
Must never block authentication, billing resolution or data review/export. Must never destroy data.

## Failure modes
Over-blocking locks the teacher out of paying (prevented by the always-permitted categories from BILL-WU-010).

## Acceptance criteria
- **AC-BILL-013-1:** (placeholder, finalized after BILL-DEC-02) Every endpoint category has a decided allowed/blocked/read-only rule for teacher and student actors when access is not granted, and a test per category.
- **AC-BILL-013-2:** In the not-granted state the teacher can authenticate, reach all billing endpoints, and export or review their data.
- **AC-BILL-013-3:** No row is deleted or altered by entering or leaving the not-granted state.

## Verification methods & required evidence
Integration tests per category; review against the BILL-DEC-02 record.

## Dependencies required before execution
BILL-DEC-02; BILL-WU-011.

## Completion definition
AC-1..3 VERIFIED against the decided ruleset.

## Commit boundaries
`feat(billing): enforce access-not-granted ruleset`; `test(billing): cover restricted-access ruleset`.

## Escalation conditions
Any attempt to start this unit before BILL-DEC-02 is recorded.
