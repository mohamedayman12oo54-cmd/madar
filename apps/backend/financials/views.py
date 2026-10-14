from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment
from accounts.permissions import IsTeacher
from config.months import current_month, parse_month
from environments.tenancy import IsEnvironmentMember

from .models import MonthlyPayment
from .serializers import PaymentHistorySerializer, PaymentUpsertSerializer

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
MAX_ROWS = 1000


class MonthlyPaymentsView(APIView):
    """GET: the month's payment sheet — every ACTIVE student of the caller's
    environment with their status for that month (unpaid when no row yet) plus
    the totals. PUT: record paid/unpaid for one student-month."""

    permission_classes = IS_ENV_OWNER

    def get(self, request):
        p = request.query_params
        month = parse_month(p.get("month") or current_month().strftime("%Y-%m"))
        env = request.environment
        qs = Enrollment.objects.filter(environment=env, is_active=True).select_related("grade")
        if gid := p.get("grade_id"):
            qs = qs.filter(grade_id=gid)
        if grp := p.get("group_id"):
            qs = qs.filter(groups__id=grp)
        if search := p.get("search", "").replace("\x00", "").strip():
            qs = qs.filter(student_name__icontains=search)
        enrollments = list(qs.distinct().order_by("student_name", "id")[:MAX_ROWS])
        rows_by_enrollment = {
            r.enrollment_id: r
            for r in MonthlyPayment.objects.filter(environment=env, month=month, enrollment_id__in=[e.id for e in enrollments])
        }
        want = p.get("status")
        rows, expected, collected, paid_n = [], Decimal("0"), Decimal("0"), 0
        for e in enrollments:
            rec = rows_by_enrollment.get(e.id)
            amount = rec.amount if rec else e.grade.fee_amount
            status_ = rec.status if rec else MonthlyPayment.Status.UNPAID
            expected += amount
            if status_ == MonthlyPayment.Status.PAID:
                collected += amount
                paid_n += 1
            if want in ("paid", "unpaid") and status_ != want:
                continue
            rows.append({
                "enrollment_id": e.id, "name": e.display_name, "grade": e.grade.name,
                "status": status_, "amount": str(amount), "paid_at": rec.paid_at if rec else None,
                "note": rec.note if rec else "",
            })
        return Response({
            "month": month.strftime("%Y-%m"),
            "rows": rows,
            "summary": {
                "students": len(enrollments), "paid": paid_n, "unpaid": len(enrollments) - paid_n,
                "expected_total": str(expected), "collected_total": str(collected),
                "outstanding_total": str(expected - collected),
            },
        })

    def put(self, request):
        ser = PaymentUpsertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        env = request.environment
        enrollment = generics.get_object_or_404(
            Enrollment.objects.filter(environment=env).select_related("grade"), pk=v["enrollment_id"]
        )
        if not enrollment.is_active:
            raise serializers.ValidationError({"detail": "الطالب غير نشط."})
        paid = v["status"] == MonthlyPayment.Status.PAID
        for _ in range(2):
            try:
                with transaction.atomic():
                    rec, created = MonthlyPayment.objects.select_for_update().get_or_create(
                        enrollment=enrollment, month=v["month"],
                        defaults={"environment": env, "amount": enrollment.grade.fee_amount, "status": v["status"],
                                  "paid_at": timezone.now() if paid else None, "note": v["note"]},
                    )
                    if not created:
                        rec.status, rec.note = v["status"], v["note"]
                        rec.paid_at = (rec.paid_at or timezone.now()) if paid else None
                        rec.save()
                break
            except IntegrityError:
                continue
        return Response({
            "enrollment_id": enrollment.id, "month": v["month"].strftime("%Y-%m"),
            "status": rec.status, "amount": str(rec.amount), "paid_at": rec.paid_at, "note": rec.note,
        })


class PaymentHistoryView(generics.ListAPIView):
    """All recorded months of ONE student in the caller's environment."""

    permission_classes = IS_ENV_OWNER
    serializer_class = PaymentHistorySerializer
    pagination_class = None

    def get_queryset(self):
        enrollment = generics.get_object_or_404(
            Enrollment.objects.filter(environment=self.request.environment), pk=self.kwargs["enrollment_id"]
        )
        return MonthlyPayment.objects.filter(environment=self.request.environment, enrollment=enrollment)
