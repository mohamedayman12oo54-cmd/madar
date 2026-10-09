from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsStudent, IsTeacher

from .models import Environment, EnvironmentMembership
from .serializers import StudentEnvironmentSerializer, TeacherEnvironmentSerializer
from .tenancy import IsEnvironmentMember


def _active_environment_ids(user):
    """Environments where THIS student is currently ACTIVE (a teacher can
    deactivate them; other teachers' environments are unaffected)."""
    from academics.models import Enrollment

    return Enrollment.objects.filter(student_id=user.id, is_active=True).values_list("environment_id", flat=True)


class TeacherEnvironmentListView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request):
        envs = Environment.objects.filter(owner=request.user)
        data = TeacherEnvironmentSerializer(envs, many=True, context={"request": request}).data
        return Response(data)


class TeacherEnvironmentEnterView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, pk):
        membership = EnvironmentMembership.objects.filter(
            environment_id=pk, environment__owner=request.user, user=request.user
        ).first()
        if not membership:
            return Response({"detail": "بيئة غير موجودة."}, status=status.HTTP_404_NOT_FOUND)
        membership.last_accessed_at = timezone.now()
        membership.save(update_fields=["last_accessed_at"])
        return Response({"environment_id": membership.environment_id})


class StudentEnvironmentListView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        memberships = EnvironmentMembership.objects.filter(
            user=request.user, role=EnvironmentMembership.Role.STUDENT,
            environment_id__in=_active_environment_ids(request.user),
        ).select_related("environment", "environment__owner")
        data = StudentEnvironmentSerializer(memberships, many=True).data
        return Response(data)


class StudentEnvironmentEnterView(APIView):
    permission_classes = [IsStudent]

    def post(self, request, pk):
        membership = EnvironmentMembership.objects.filter(
            environment_id=pk, user=request.user, role=EnvironmentMembership.Role.STUDENT,
            environment_id__in=_active_environment_ids(request.user),
        ).first()
        if not membership:
            return Response({"detail": "بيئة غير موجودة."}, status=status.HTTP_404_NOT_FOUND)
        membership.last_accessed_at = timezone.now()
        membership.save(update_fields=["last_accessed_at"])
        return Response({"environment_id": membership.environment_id})

class EnvironmentContextView(APIView):
    """GET /api/v1/environments/context/ — the reference implementation of
    server-side active-environment resolution (Phase 1). Given a valid
    `X-Madar-Environment` header naming an environment the caller belongs
    to, confirms it and returns just enough for the frontend to render a
    "you are here" indicator and to validate a *persisted* selection (e.g.
    on page reload) before trusting it for any tenant-scoped call.

    Every future tenant-scoped endpoint (Phase 2+) authorizes the exact
    same way, via IsEnvironmentMember — this view has no special-cased
    logic of its own beyond that permission check.
    """

    permission_classes = [IsEnvironmentMember]

    def get(self, request):
        env = request.environment
        membership = request.environment_membership
        data = {"id": env.id, "name": env.name, "role": membership.role}
        if membership.role == EnvironmentMembership.Role.STUDENT:
            data["owner"] = {"name": env.owner.name, "initials": env.owner.initials}
        else:
            data["initials"] = env.initials
        return Response(data)


class EnvironmentSettingsView(APIView):
    """The teacher's current environment (header-scoped): read + rename.
    Owner-only. Environment cardinality / creation of extra environments is
    deliberately NOT here: the docs leave it unresolved."""

    permission_classes = [IsTeacher, IsEnvironmentMember.for_role("owner")]

    def _data(self, env):
        return {"id": env.id, "name": env.name, "subject_stage": env.subject_stage,
                "academic_year": env.academic_year, "created_at": env.created_at}

    def get(self, request):
        return Response(self._data(request.environment))

    def patch(self, request):
        env = request.environment
        allowed = {"name", "subject_stage"}
        if not isinstance(request.data, dict) or set(request.data) - allowed:
            return Response({"detail": "يمكن تعديل الاسم والمرحلة فقط.", "code": "validation_error"}, status=400)
        fields = {}
        if "name" in request.data:
            name = str(request.data["name"]).strip()
            if not (2 <= len(name) <= 150):
                return Response({"detail": "تحقق من البيانات المدخلة.", "code": "validation_error",
                                 "fields": {"name": "اسم البيئة بين حرفين و150 حرفًا."}}, status=400)
            fields["name"] = name
            fields["initials"] = name[:1]
        if "subject_stage" in request.data:
            stage = str(request.data["subject_stage"]).strip()
            if len(stage) > 150:
                return Response({"detail": "تحقق من البيانات المدخلة.", "code": "validation_error",
                                 "fields": {"subject_stage": "النص طويل جدًا."}}, status=400)
            fields["subject_stage"] = stage
        for k, v in fields.items():
            setattr(env, k, v)
        env.save(update_fields=list(fields) or None)
        return Response(self._data(env))


class OverviewView(APIView):
    """Real, server-computed dashboard numbers for the caller's own environment
    (never client-supplied, never fabricated). All aggregates are filtered by
    `request.environment`."""

    permission_classes = [IsTeacher, IsEnvironmentMember.for_role("owner")]

    def get(self, request):
        from decimal import Decimal

        from django.db.models import Count, Q

        from academics.models import Enrollment, Grade, Group
        from config.months import current_month
        from financials.models import MonthlyPayment
        from notifications.models import Notification
        from scheduling.models import SessionInstance

        env = request.environment
        today = timezone.localdate()
        month = current_month()
        enrollments = Enrollment.objects.filter(environment=env)
        active = enrollments.filter(is_active=True)
        sessions = SessionInstance.objects.filter(environment=env)
        todays = sessions.filter(scheduled_at__date=today).select_related("group").order_by("scheduled_at")
        upcoming = sessions.filter(status="planned", scheduled_at__gte=timezone.now()).select_related("group").order_by("scheduled_at")[:5]

        expected = sum((e.grade.fee_amount for e in active.select_related("grade")), Decimal("0"))
        paid_rows = MonthlyPayment.objects.filter(environment=env, month=month, status="paid", enrollment__is_active=True)
        collected = sum((p.amount for p in paid_rows), Decimal("0"))
        notif = {r["delivery_status"]: r["n"] for r in Notification.objects.filter(environment=env).values("delivery_status").annotate(n=Count("id"))}

        def money(value):
            return str(Decimal(value).quantize(Decimal("0.01")))

        def brief(s):
            return {"id": s.id, "group": s.group.name, "scheduled_at": s.scheduled_at, "status": s.status}

        return Response({
            "environment": {"name": env.name, "academic_year": env.academic_year},
            "students": {"active": active.count(), "inactive": enrollments.filter(is_active=False).count()},
            "structure": {"grades": Grade.objects.filter(environment=env).count(), "groups": Group.objects.filter(environment=env).count()},
            "sessions": {
                "today": [brief(s) for s in todays],
                "open": sessions.filter(status="open").count(),
                "upcoming": [brief(s) for s in upcoming],
            },
            "payments": {
                "month": month.strftime("%Y-%m"), "paid": paid_rows.count(), "students": active.count(),
                "expected_total": money(expected), "collected_total": money(collected),
                "outstanding_total": money(expected - collected),
            },
            "notifications": {"pending": notif.get("pending", 0), "failed": notif.get("failed", 0)},
        })
