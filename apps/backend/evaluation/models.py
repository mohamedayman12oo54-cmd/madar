"""
Phase 4 / Student Evaluation.

UNRESOLVED PRODUCT DECISION (flagged, not guessed): the spec explicitly warns
against inventing a grading system, but does not define one either (no
percentage scores, rubric categories, or pass/fail scheme are specified).
Per its own instruction ("implement the minimum required structure, clearly
mark any remaining product decision"), this phase implements only the two
concepts the spec names explicitly and independently:

- TeacherNote: a free-text note about a student, optionally tied to a
  specific Session (this doubles as "recitation / educational activity" —
  the spec ties that to "the appropriate educational relationship/session
  context" without defining a scoring scheme for it either, so a session-
  scoped note is the minimum structure that satisfies it without inventing
  one).
- Rating: a small 1–5 integer, optionally tied to a specific Session.

Both are scoped to an Enrollment (never a bare Student — same ownership
boundary as Attendance/Payment) and, when a Session is given, that session's
group must match the enrollment's group (same cross-check pattern as
AttendanceRecord).

Actual grading/scoring semantics remain an open product decision for a
future phase.
"""
from django.core.exceptions import ValidationError
from django.db import models

from academics.models import Enrollment
from environments.tenancy import TenantOwnedModel
from scheduling.models import SessionInstance


class _SessionScopedMixin(models.Model):
    """Shared validation for TeacherNote/Rating: if a session is given, it
    must belong to the same environment AND the same group as the
    enrollment — identical rule to AttendanceRecord.clean() in
    scheduling/models.py."""

    class Meta:
        abstract = True

    def clean(self):
        if self.enrollment_id and self.environment_id and self.enrollment.environment_id != self.environment_id:
            raise ValidationError("السجل يجب أن ينتمي لنفس بيئة تسجيل الطالب.")
        if self.session_id:
            if self.session.environment_id != self.environment_id:
                raise ValidationError("الجلسة المرتبطة يجب أن تنتمي لنفس البيئة.")
            if self.enrollment_id and self.session.group_id != self.enrollment.group_id:
                raise ValidationError("لا يمكن ربط سجل بجلسة لا تخص مجموعة هذا الطالب.")


class TeacherNote(_SessionScopedMixin, TenantOwnedModel):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="notes")
    session = models.ForeignKey(SessionInstance, on_delete=models.SET_NULL, null=True, blank=True, related_name="notes")
    body = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"note on {self.enrollment} ({self.created_at:%Y-%m-%d})"


class Rating(_SessionScopedMixin, TenantOwnedModel):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="ratings")
    session = models.ForeignKey(SessionInstance, on_delete=models.SET_NULL, null=True, blank=True, related_name="ratings")
    value = models.PositiveSmallIntegerField()  # 1..5 — enforced in the serializer
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.value}/5 on {self.enrollment} ({self.created_at:%Y-%m-%d})"
