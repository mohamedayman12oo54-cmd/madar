# BILL-WU-041 — AI usage quotas / cost controls

**ID:** BILL-WU-041 · **Workstream/Package:** BILL-WS-K / BILL-WP-K1
**Status:** OUT OF SCOPE
**Reason:** commercial-model §Open items: "AI usage quotas / cost controls (ties to the Plan 3 future-feature rule) — Open"; backend open-items: "Targeted abuse/cost protection on AI operations — Conditional."
**Priority / Risk:** — / Medium (Plan 3 has no numerical cap; unbounded AI cost exposure, BILL-RISK-09)

## Purpose
Tracked placeholder. This plan gates AI **availability** per plan (BILL-WU-011) and does not meter **usage**.

## Expected outcome
None in this plan.

## Requirement / invariant references
commercial-model §Plan 3 future-feature rule, §Open items.

## Relevant ADRs / contracts
ADR-006, ADR-018.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| Quota/cost-control policy (product) | DECISION | Yes, for any future version | Open |

## Preconditions
Not applicable.

## In-scope changes
None.

## Explicit exclusions
Per-plan rate limits, token counting, monthly AI allowances.

## Implementation surfaces (grounded at bf115df)
None. A future version would sit beside `billing/entitlements.py` and `ai/views.py`.

## Data-integrity & security considerations
Not applicable.

## Failure modes
AI cost overrun (only a stub provider exists today, `settings.py:229`, so this is latent).

## Acceptance criteria
- **AC-BILL-041-1:** No quota logic is introduced by this plan (review).

## Verification methods & required evidence
Review.

## Dependencies required before execution
Not planned.

## Completion definition
Remains OUT OF SCOPE until re-scoped.

## Commit boundaries
None.

## Escalation conditions
A real LLM provider goes live before a quota decision exists.
