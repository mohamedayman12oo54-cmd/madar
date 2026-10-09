"""
Payment tracking — exactly what the documentation specifies (glossary,
functional.md, INV-5): a RECORD of the student's MONTHLY fee status, one row
per Enrollment x Calendar Month, paid/unpaid + amount. Record-only: no online
processing, no accounting, no partial payments, no discounts.

The fee is owned by the GRADE. The amount stored on a row is the grade fee in
force when the row was first recorded and is never typed by the client, so a
later fee change cannot rewrite history (INV-6) and nobody can invent a
discount by sending an arbitrary amount.
"""
from django.core.exceptions import ValidationError
from django.db import models

from academics.models import Enrollment
from environments.tenancy import TenantOwnedModel


class MonthlyPayment(TenantOwnedModel):
    class Status(models.TextChoices):
        PAID = "paid", "مدفوع"
        UNPAID = "unpaid", "غير مدفوع"

    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="monthly_payments")
    month = models.DateField()  # always the first day of the month
    status = models.CharField(max_length=6, choices=Status.choices, default=Status.UNPAID)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(null=True, blank=True)
    note = models.CharField(max_length=200, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-month", "enrollment_id"]
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "month"], name="unique_payment_per_enrollment_month"),
            models.CheckConstraint(condition=models.Q(amount__gte=0), name="monthly_payment_amount_non_negative"),
        ]

    def clean(self):
        if self.enrollment_id and self.enrollment.environment_id != self.environment_id:
            raise ValidationError("الدفعة يجب أن تنتمي لنفس بيئة تسجيل الطالب.")
        if self.month and self.month.day != 1:
            raise ValidationError("الشهر يجب أن يكون أول يوم في الشهر.")
