# BILL-WU-009 — Plan catalog and capability keys

**ID:** BILL-WU-009 · **Workstream/Package:** BILL-WS-B / BILL-WP-B1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** BILL-DEC-07 (mapping of plan features to existing code capabilities). In particular, Plan 2's
"AI chat about video-lesson content" has no matching implementation: the existing `assistant` kind is a
**general** KB tutor (`ai/models.py:17-21`). There is also the question of whether the general Study
Assistant is plan-gated at all.
**Priority / Risk:** P1 / Medium

## Purpose
Seed the three decided plans exactly as `commercial-model.md` §Plans states, and define stable
**capability keys** that the entitlement contract and enforcement points use, so feature gating has one
vocabulary.

## Expected outcome
A data migration creates Plan 1 (EGP 1,000; cap 400), Plan 2 (EGP 1,500; cap 800) and Plan 3 (EGP 2,000; no
plan-level cap), each with a 30-elapsed-day period. A code-level capability registry (e.g.,
`billing/capabilities.py`) defines keys:
- `ai.quiz_from_video` (Plans 1, 2, 3; trial)
- `ai.video_content_chat` (Plans 2, 3; trial). **Key defined; no backing feature exists yet (BILL-DEC-07)**
- `ai.performance_analysis` (Plan 3; trial). Candidate mapping is `state_recommendation`
  (`ai/models.py:22-27`), but the commercial definition (attendance, recitation, quizzes, video-watch
  ratio) is wider than the current evidence snapshot, so record a mapping decision
- trial = Plan 3 feature set, cap 250 (commercial-model §Free trial)

No additional tier, annual option or discount is representable.

## Requirement / invariant references
commercial-model §Plans, §Free trial; functional §Billing bullet 1.

## Relevant ADRs / contracts
ADR-014, ADR-018.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-008 | BLOCKING | Yes | Plan table |
| BILL-DEC-07 | DECISION | Non-blocking (key exists; mapping recorded as open) | Feature-to-code mapping |

## Preconditions
Re-read commercial-model §Plans at execution time. The numbers come **only** from there.

## In-scope changes
Data migration; capability registry; tests.

## Explicit exclusions
Building the Plan 2 chat feature; changing prices at runtime (price-change policy is open, BILL-WU-042); the
Plan 3 future-feature separate-pricing mechanism (open).

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/migrations/0002_seed_plans.py`, `apps/backend/billing/capabilities.py`. Existing
AI kinds: `apps/backend/ai/models.py:48-51`.

## Data-integrity & security considerations
Plans are read-only to clients; prices are never accepted from requests. The migration is idempotent (keyed by plan identity).

## Failure modes
Numbers drift from the commercial doc (test pins the exact values against a single constant table, reviewed against the doc).

## Acceptance criteria
- **AC-BILL-009-1:** Exactly three plans exist after migration, with prices 1000/1500/2000 EGP, caps 400/800/none, and a 30-day period.
- **AC-BILL-009-2:** The capability registry maps each plan and the trial to exactly the feature sets in commercial-model; the trial equals Plan 3 features with cap 250.
- **AC-BILL-009-3:** The BILL-DEC-07 mapping status is recorded in the module docstring and in `risks-and-open-issues.md` (no silent mapping).

## Verification methods & required evidence
Data-migration test; unit test of the registry; review record.

## Dependencies required before execution
BILL-WU-008.

## Completion definition
AC-1..3 VERIFIED.

## Commit boundaries
`feat(billing): seed the three plans and define capability keys`.

## Escalation conditions
Any request to add a plan, discount or annual billing; any decision that the general Study Assistant is plan-gated (affects student-facing behaviour, so it is System-level).
