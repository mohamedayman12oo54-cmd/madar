from decimal import Decimal

from django.db.models import Sum
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment
from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import Payment
from .serializers import (
    EnrollmentFinancialSummarySerializer,
    PaymentCreateSerializer,
    PaymentSerializer,
    PaymentUpdateSerializer,
)

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]


class PaymentListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = Payment.objects.select_related("enrollment__student")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if enrollment_id := params.get("enrollment_id"):
            qs = qs.filter(enrollment_id=enrollment_id)
        if grade_id := params.get("grade_id"):
            qs = qs.filter(enrollment__grade_id=grade_id)
        return qs

    def get_serializer_class(self):
        return PaymentCreateSerializer if self.request.method == "POST" else PaymentSerializer


class PaymentDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = Payment.objects.select_related("enrollment__student")

    def get_serializer_class(self):
        return PaymentUpdateSerializer if self.request.method in ("PUT", "PATCH") else PaymentSerializer


class FinancialSummaryView(APIView):
    """GET /api/v1/financials/summary/?grade_id=&group_id= — one row per
    Enrollment in scope: the grade's fee (Grade owns it — Phase 2), how much
    has been paid against it, and what's outstanding. Never stored — always
    computed fresh from Payment rows, so it can never drift out of sync with
    the ledger."""

    permission_classes = IS_ENV_OWNER

    def get(self, request):
        qs = (
            Enrollment.objects.filter(environment=request.environment, is_active=True)
            .select_related("student", "grade")
        )
        if grade_id := request.query_params.get("grade_id"):
            qs = qs.filter(grade_id=grade_id)
        if group_id := request.query_params.get("group_id"):
            qs = qs.filter(group_id=group_id)
        qs = qs.annotate(paid=Sum("payments__amount"))

        rows = []
        for e in qs:
            paid_total = e.paid or Decimal("0.00")
            rows.append(
                {
                    "enrollment_id": e.id,
                    "student_id": e.student_id,
                    "student_name": e.student.name,
                    "grade_id": e.grade_id,
                    "grade_name": e.grade.name,
                    "fee_amount": e.grade.fee_amount,
                    "paid_total": paid_total,
                    "outstanding": e.grade.fee_amount - paid_total,
                }
            )
        return Response(EnrollmentFinancialSummarySerializer(rows, many=True).data)
