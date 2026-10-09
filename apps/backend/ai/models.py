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

The AI Study Assistant is a GENERAL educational tutor. This model
deliberately has NO foreign key to Enrollment/Student/Session/Payment/Note —
so it is structurally impossible for an operation to be "about" a specific
student's private records, or for one to retrieve them. (Spec: "Do not
silently turn it into a personalized student-record retrieval system.")
The only relations are the environment (tenancy) and the requesting user.

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

    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ai_operations")
    prompt = models.TextField()
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
            models.UniqueConstraint(
                fields=["environment", "requested_by", "idempotency_key"],
                condition=Q(idempotency_key__isnull=False),
                name="unique_ai_idempotency_key_per_user_env",
            ),
        ]

    def __str__(self):
        return f"AIOperation#{self.pk} [{self.status}]"
