"""
Phase 5 / AI — an INTERNAL bounded module of the monolith.

Lifecycle (spec: "SUBMIT -> OPERATION ID -> POLL STATUS -> RESULT"):

    pending -> processing -> completed
                          \\-> failed

- Submission (the API) only ever inserts a `pending` row and returns its id.
  It never calls a model. A separate worker (management command
  `process_ai_operations`) does the slow part — see providers.py.
- The result is persisted HERE, in Madar's own database. The model provider
  is not the source of truth; once `completed`, polling never goes back to it.
- Failures are explicit (`failed` + `error`); a failed operation never leaves
  partial state anywhere else — nothing else is written by this app at all.

Two kinds of operation (docs: scope.md, PD-1):
- `assistant`: the Study Assistant, a GENERAL educational tutor. It is
  structurally forbidden (CheckConstraint below) from referencing any student:
  no enrollment, no month, no evidence.
- `quiz_generation`: a STUDENT-initiated quiz built from teacher-provided
  content. Its input is a frozen snapshot of that content's title/text only.
- `state_recommendation`: an ADVISORY suggestion of a monthly State for ONE
  enrollment. Its input is a bounded, aggregate `evidence` snapshot (counts
  only — no names, no notes) captured when the teacher asks, so the worker
  never needs to read tenant data. The teacher always finalizes the State; the
  suggestion is never applied automatically.

Idempotency is SELECTIVE, not universal (spec): a client may send an optional
`idempotency_key` on submit; a partial unique constraint (only when a key is
present) makes a retried submit return the same operation instead of
creating a duplicate. Submissions without a key are always new operations.
"""
from django.conf import settings
from django.db import models
from django.db.models import Q

from environments.tenancy import TenantOwnedModel


class AIOperation(TenantOwnedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        PROCESSING = "processing", "قيد المعالجة"
        COMPLETED = "completed", "مكتملة"
        FAILED = "failed", "فشلت"

    class Kind(models.TextChoices):
        ASSISTANT = "assistant", "المساعد الدراسي"
        STATE_RECOMMENDATION = "state_recommendation", "اقتراح حالة الطالب"
        QUIZ_GENERATION = "quiz_generation", "توليد اختبار"

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_operations")
    kind = models.CharField(max_length=24, choices=Kind.choices, default=Kind.ASSISTANT)
    enrollment = models.ForeignKey("academics.Enrollment", on_delete=models.CASCADE, null=True, blank=True, related_name="+")
    content = models.ForeignKey("content.ContentItem", on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    month = models.DateField(null=True, blank=True)
    evidence = models.JSONField(default=dict, blank=True)
    suggested_state = models.CharField(max_length=20, blank=True)
    prompt = models.TextField()
    # The PUBLISHED KB documents this answer was grounded in (assistant kind
    # only): [{"id","title","topic","version"}]. Empty means the KB had no
    # relevant material — the answer must say so rather than invent one.
    sources = models.JSONField(default=list, blank=True)
    idempotency_key = models.CharField(max_length=64, null=True, blank=True)

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    result = models.TextField(blank=True)
    error = models.CharField(max_length=255, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(
                condition=Q(kind__in=["state_recommendation", "quiz_generation"]) | Q(enrollment__isnull=True, month__isnull=True),
                name="assistant_operations_never_reference_a_student",
            ),
            models.UniqueConstraint(
                fields=["environment", "requested_by", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_ai_idempotency_key_per_user_env",
            ),
        ]

    def __str__(self):
        return f"AIOperation#{self.pk} [{self.status}]"
