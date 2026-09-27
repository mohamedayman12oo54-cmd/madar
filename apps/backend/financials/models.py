"""
Phase 4 / Financials.

Domain rule enforced here (from the spec, not invented): GRADE OWNS THE FEE
(academics.Grade.fee_amount, added in Phase 2, unused until now). Payment
does NOT duplicate or override that — a Payment is a record of money
received against an Enrollment; "how much is still owed" is always computed
as `enrollment.grade.fee_amount - sum(payments)`, never stored redundantly.

UNRESOLVED PRODUCT DECISION (flagged, not guessed): the spec does not say
whether Grade.fee_amount is a one-time fee, a per-academic-year fee, or a
recurring (e.g. monthly) fee. This phase treats it as the total owed for the
Enrollment's academic year — the smallest assumption consistent with
"Enrollment stores the applicable Academic Year" and "Grade owns the fee" —
and does NOT invent a billing period, due dates, or installment plans on top
of that. See PHASE_README's Assumptions section.
"""
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from academics.models import Enrollment
from environments.tenancy import TenantOwnedModel


class Payment(TenantOwnedModel):
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="payments")
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_at = models.DateTimeField(default=timezone.now)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-paid_at"]

    def clean(self):
        if self.enrollment_id and self.environment_id and self.enrollment.environment_id != self.environment_id:
            raise ValidationError("الدفعة يجب أن تنتمي لنفس بيئة تسجيل الطالب.")

    def __str__(self):
        return f"{self.amount} — {self.enrollment}"
