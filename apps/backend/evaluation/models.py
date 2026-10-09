"""
Student Evaluation (docs: glossary / functional.md):
  - State  : per Enrollment x Calendar Month, controlled vocabulary
             Good | Needs Follow-up | At Risk. Teacher FINALIZES; an AI
             recommendation (ai app) is advisory only.
  - Rating : per Enrollment x Calendar Month, teacher-assigned 1-5, distinct
             from State. It is a draft until the teacher PUBLISHES it; only
             publishing fires the "monthly rating published" notification and
             makes it visible to the student.
  - Private notes : teacher-only, never exposed to students.
"""
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from academics.models import Enrollment
from environments.tenancy import TenantOwnedModel


class _EnrollmentScoped(TenantOwnedModel):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True

    def clean(self):
        if self.enrollment_id and self.enrollment.environment_id != self.environment_id:
            raise ValidationError("السجل يجب أن ينتمي لنفس بيئة تسجيل الطالب.")


class PrivateNote(_EnrollmentScoped):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="private_notes")
    body = models.TextField(max_length=2000)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class MonthlyRating(_EnrollmentScoped):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="monthly_ratings")
    month = models.DateField()
    value = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(5)])
    published_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month", "enrollment_id"]
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "month"], name="unique_rating_per_enrollment_month"),
            models.CheckConstraint(condition=models.Q(value__gte=1, value__lte=5), name="monthly_rating_1_to_5"),
        ]


class StudentState(_EnrollmentScoped):
    class State(models.TextChoices):
        GOOD = "good", "جيد"
        NEEDS_FOLLOW_UP = "needs_follow_up", "يحتاج متابعة"
        AT_RISK = "at_risk", "معرّض للخطر"

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="monthly_states")
    month = models.DateField()
    state = models.CharField(max_length=20, choices=State.choices)
    finalized_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, related_name="+")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month", "enrollment_id"]
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "month"], name="unique_state_per_enrollment_month"),
        ]
