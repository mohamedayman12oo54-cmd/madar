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

Every plan grants every capability: the plans (monthly / term / yearly) differ in price and in how long one
paid period lasts, which is `Plan.period_days` (applied by `BillingPeriod` rows, BILL-WU-024), not in features.

Student-count caps are read directly from `Plan.max_students` / this
module's `TRIAL_STUDENT_CAP`, not from a separate table — BILL-WU-012 is
where cap *enforcement* happens; this module only names the numbers.
"""
from .models import Plan

AI_QUIZ_FROM_VIDEO = "ai.quiz_from_video"
AI_VIDEO_CONTENT_CHAT = "ai.video_content_chat"
AI_PERFORMANCE_ANALYSIS = "ai.performance_analysis"

ALL_CAPABILITIES = frozenset({AI_QUIZ_FROM_VIDEO, AI_VIDEO_CONTENT_CHAT, AI_PERFORMANCE_ANALYSIS})

# One feature set for every plan: whichever way a teacher pays, they get everything.
PLAN_CAPABILITIES = {
    Plan.Key.MONTHLY: ALL_CAPABILITIES,
    Plan.Key.TERM: ALL_CAPABILITIES,
    Plan.Key.YEARLY: ALL_CAPABILITIES,
}

# The 16-day free trial = every feature, with its OWN student cap (250): the plans themselves have no cap.
TRIAL_CAPABILITIES = ALL_CAPABILITIES
TRIAL_STUDENT_CAP = 250


def capabilities_for_plan(plan_key):
    """Return the frozenset of capability keys the given Plan.Key grants.
    Raises KeyError for anything that is not one of the three decided plan
    keys — there is no plan this registry doesn't know about, by design."""
    return PLAN_CAPABILITIES[plan_key]
