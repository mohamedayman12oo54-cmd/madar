"""
The processing of ONE AI operation, shared by the two ways an operation gets worked on:

* the `process_ai_operations` command (cron / `--loop`), and
* the in-process dispatcher (ai/dispatch.py), which starts the work right after the request is saved so
  nobody has to run a separate worker for the product to answer.

Both go through `claim()`, a single conditional UPDATE (pending -> processing): however many workers
and threads race for a row, exactly one of them calls the provider.

BILL-WU-011 (OP-PARITY): for the two plan-gated kinds the entitlement is re-checked right after claiming and
before any provider call; a capability lost between submit and processing ends the operation `failed`
with a stable message (ADR-006: no partial result).
"""
import logging

from django.db import transaction
from django.utils import timezone

from ai.models import AIOperation
from ai.providers import AIProviderError, get_provider, validate_questions
from billing import capabilities, entitlements
from knowledge.retrieval import as_citations, as_context, select_sources

log = logging.getLogger(__name__)

# BILL-WU-011 / OP-PARITY: the two plan-gated kinds and the capability each one
# needs. `assistant` is deliberately absent (BILL-DEC-07: not gated until decided).
GATED_KIND_CAPABILITIES = {
    AIOperation.Kind.STATE_RECOMMENDATION: capabilities.AI_PERFORMANCE_ANALYSIS,
    AIOperation.Kind.QUIZ_GENERATION: capabilities.AI_QUIZ_FROM_VIDEO,
}
# Stable, client-safe error stored when the capability was lost between submit and processing.
ENTITLEMENT_LOST_ERROR = "انتهت صلاحية الباقة المطلوبة لهذه الميزة قبل تنفيذ الطلب."

COMPLETED, FAILED = "completed", "failed"


def claim(op_id: int) -> bool:
    """Atomically move ONE operation pending -> processing. A single
    conditional UPDATE: of any number of concurrent callers, exactly one
    sees a matching row and gets True."""
    return bool(
        AIOperation.objects.filter(pk=op_id, status=AIOperation.Status.PENDING).update(
            status=AIOperation.Status.PROCESSING, started_at=timezone.now()
        )
    )


def run_claimed(op_id: int) -> str:
    """Do the work for an operation this caller has ALREADY claimed. -> COMPLETED or FAILED."""
    op = AIOperation.objects.get(pk=op_id)

    required_capability = GATED_KIND_CAPABILITIES.get(op.kind)
    if required_capability is not None:
        decision = entitlements.decide(op.environment)
        if required_capability not in decision.capabilities:
            op.status = AIOperation.Status.FAILED
            op.error = ENTITLEMENT_LOST_ERROR
            op.result = ""
            op.suggested_state = ""
            op.sources = []
            op.completed_at = timezone.now()
            op.save(update_fields=["status", "result", "error", "completed_at", "suggested_state", "sources"])
            return FAILED

    questions = None
    try:
        # The (slow) provider call happens OUTSIDE any transaction/lock.
        if op.kind == AIOperation.Kind.QUIZ_GENERATION:
            quiz = get_provider().generate_quiz_result(op.evidence)
            questions = validate_questions(quiz.questions)
            op.metadata = quiz.metadata
            result = "quiz-ready"
        elif op.kind == AIOperation.Kind.STATE_RECOMMENDATION:
            op.suggested_state, result = get_provider().recommend_state(op.evidence)
        else:
            # Study Assistant: ground the answer in the central curated
            # KB (docs: scope.md "Study Assistant <- central curated
            # Knowledge Base"). Only PUBLISHED documents are
            # authoritative, and the exact ones used are persisted so
            # the answer can show its sources.
            docs = select_sources(op.prompt)
            result = get_provider().generate(op.prompt, as_context(docs))
            op.sources = as_citations(docs)
    except Exception as exc:  # any provider failure -> explicit `failed`
        message = str(exc) if isinstance(exc, AIProviderError) else "تعذّر إكمال الطلب."
        op.status = AIOperation.Status.FAILED
        op.error = message[:255]
        op.result = ""
        op.suggested_state = ""
        op.sources = []
        # For operators only (never serialized to clients). Category and
        # exception TYPE, never the message: it may carry provider text.
        op.metadata = getattr(exc, "metadata", None) or {
            "validation": "failed", "failure_category": "unexpected", "exception": type(exc).__name__}
        log.warning("ai operation failed op=%s kind=%s category=%s",
                    op.pk, op.kind, op.metadata.get("failure_category"))
    else:
        op.status = AIOperation.Status.COMPLETED
        op.result = result
        op.error = ""
    op.completed_at = timezone.now()
    with transaction.atomic():
        # The quiz is persisted in the SAME transaction that marks the
        # operation completed: a crash can never leave "completed but
        # no quiz", and a failed operation never leaves a partial quiz.
        if op.status == AIOperation.Status.COMPLETED and op.kind == AIOperation.Kind.QUIZ_GENERATION:
            from studentarea.models import Quiz

            Quiz.objects.create(
                environment_id=op.environment_id, enrollment_id=op.enrollment_id, content_id=op.content_id,
                content_title=op.evidence.get("title", "")[:200], operation=op, questions=questions,
            )
        op.save(update_fields=["status", "result", "error", "completed_at", "suggested_state", "sources", "metadata"])
    return COMPLETED if op.status == AIOperation.Status.COMPLETED else FAILED


def process_operation(op_id: int):
    """Claim and run one operation. -> COMPLETED / FAILED, or None when another worker already took it."""
    if not claim(op_id):
        return None
    return run_claimed(op_id)
