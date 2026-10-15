"""
Billing capability registry (BILL-WU-009; BILL-DEC-07 — open mapping, not
silently resolved here).

Defines the stable vocabulary the entitlement contract (BILL-WU-010) and
later enforcement points use to ask "does this Plan/trial grant capability
X?" Recording a capability *key* here is not a claim that a real feature
backs it elsewhere in the codebase — that mapping is BILL-DEC-07, and its
status per key is:

- `ai.quiz_from_video` — backed by `ai.AIOperation.Kind.QUIZ_GENERATION`
  (`ai/models.py:51`). Mapping is solid.
- `ai.video_content_chat` — Plan 2's "AI chat about video-lesson content"
  has **no matching implementation today**. The existing `assistant` kind
  (`ai/models.py:49`) is a GENERAL knowledge-base tutor, not scoped to one
  video lesson's content. The key exists so the entitlement contract has a
  name to gate on once the feature is built; it intentionally has no
  backing capability yet (see `risks-and-open-issues.md` BILL-DEC-07).
- `ai.performance_analysis` — candidate mapping is `state_recommendation`
  (`ai/models.py:50`), but that kind's `evidence` snapshot is narrower than
  the commercial definition (attendance, recitation, quizzes, video-watch
  ratio per `commercial-model.md` §Plans). Recorded as a **candidate**, not
  a confirmed mapping.
- Whether the general Study Assistant (`assistant` kind) is plan-gated AT
  ALL is explicitly undecided and is a System-level, student-facing
  decision — not something this module resolves (this unit's own
  Escalation conditions). It is deliberately **not** listed as a
  capability key below.

`BILLING_PERIOD_DAYS` is a single global constant, not a per-Plan field:
all three plans share one identical 30-elapsed-day billing period
(`commercial-model.md` §Plans — every row in that table says "30 elapsed
days"), so there is nothing to vary per plan. `BillingPeriod` rows (not
this module) are where that constant is actually applied (BILL-WU-024).

Student-count caps are read directly from `Plan.max_students` / this
module's `TRIAL_STUDENT_CAP`, not from a separate table — BILL-WU-012 is
where cap *enforcement* happens; this module only names the numbers.
"""
from .models import Plan

AI_QUIZ_FROM_VIDEO = "ai.quiz_from_video"
AI_VIDEO_CONTENT_CHAT = "ai.video_content_chat"
AI_PERFORMANCE_ANALYSIS = "ai.performance_analysis"

# All three plans share one 30-elapsed-day billing period (commercial-model
# §Plans). Never a calendar month; see BILL-WU-024.
BILLING_PERIOD_DAYS = 30

# Each plan grants everything the plan(s) "below" it grant, plus one more
# capability — exactly as commercial-model.md §Plans states ("Everything in
# Plan 1 + ...", "Everything in Plan 2 + ...").
PLAN_CAPABILITIES = {
    Plan.Key.PLAN_1: frozenset({AI_QUIZ_FROM_VIDEO}),
    Plan.Key.PLAN_2: frozenset({AI_QUIZ_FROM_VIDEO, AI_VIDEO_CONTENT_CHAT}),
    Plan.Key.PLAN_3: frozenset({AI_QUIZ_FROM_VIDEO, AI_VIDEO_CONTENT_CHAT, AI_PERFORMANCE_ANALYSIS}),
}

# Trial = Plan 3's full feature set (commercial-model.md §Free trial), with
# its OWN student cap (250) — independent of, and smaller than, every
# plan's own cap, including Plan 3's absence of a plan-level cap.
TRIAL_CAPABILITIES = PLAN_CAPABILITIES[Plan.Key.PLAN_3]
TRIAL_STUDENT_CAP = 250


def capabilities_for_plan(plan_key):
    """Return the frozenset of capability keys the given Plan.Key grants.
    Raises KeyError for anything that is not one of the three decided plan
    keys — there is no plan this registry doesn't know about, by design
    (this unit excludes any additional tier)."""
    return PLAN_CAPABILITIES[plan_key]
