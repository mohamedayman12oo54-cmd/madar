# BILL-WU-032 — Frontend contract hand-off

**ID:** BILL-WU-032 · **Workstream/Package:** BILL-WS-I / BILL-WP-I1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** BILL-DEC-02 portions (restricted-access UI contract) can't be specified until decided, so
they are marked "pending" in the hand-off.
**Priority / Risk:** P1 / Medium

## Purpose
Give the Frontend owner a precise, versioned description of the billing contract (AL-4) so checkout, status
and restricted-state UI can be built without guessing. In particular: **a redirect back from Kashier means
"pending confirmation", never "paid".**

## Expected outcome
A contract hand-off note covering: endpoints and payloads from BILL-WU-019/028/031; stable error codes
(`entitlement_required`, `capability_not_in_plan`, `student_cap_reached`, `renewal_already_in_progress`,
etc.); polling guidance for post-checkout status; the trial-days-remaining source; cancellation messaging;
and the note that `GET /api/v1/environments/teacher/` remains a list with at most one item (INV-9). Where
it lives follows the repo's convention for API docs. Proposed:
`docs/services/backend/07-contracts/` or the API-documentation stage. Doing so is a **documentation change
by the implementer, outside this plan's own authoring**, so check with the owning layer first. Plus a PR
description shared with the Frontend owner.

## Requirement / invariant references
AL-4; ADR-016 (redirect non-trust); NODE-WireAPI.

## Relevant ADRs / contracts
`07-contracts/api-contract.md` (error contract: stable codes, separate messages).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-011, 012, 019, 028, 031 | CONTRACT | Yes | Surfaces to describe |
| BILL-DEC-02 | DECISION | Non-blocking (section marked pending) | Restricted UI |

## Preconditions
Endpoints implemented and tested.

## In-scope changes
Contract document plus hand-off record.

## Explicit exclusions
Any `apps/web` change (Frontend-owned), including the dead `apps/web/src/lib/financialsApi.js` (flagged only).

## Implementation surfaces (grounded at bf115df)
Docs location per owning layer; references `apps/backend/billing/*`.

## Data-integrity & security considerations
The document must not include secrets or sample real tokens.

## Failure modes
Frontend treats the redirect as success (mitigated by an explicit contract statement plus a Backend guarantee from BILL-WU-019).

## Acceptance criteria
- **AC-BILL-032-1:** Every billing endpoint and error code implemented is documented with request/response examples.
- **AC-BILL-032-2:** The redirect-is-pending rule is stated explicitly.
- **AC-BILL-032-3:** The Frontend owner has acknowledged receipt (recorded).
- **AC-BILL-032-4:** BILL-DEC-02-dependent sections are explicitly marked pending.

## Verification methods & required evidence
Review record; acknowledgment.

## Dependencies required before execution
BILL-WU-031, 019, 028, 011, 012.

## Completion definition
AC-1..4 met.

## Commit boundaries
`docs(billing): hand off billing API contract to frontend`.

## Escalation conditions
The Frontend needs something the Backend contract can't safely provide (e.g., client-side activation).
