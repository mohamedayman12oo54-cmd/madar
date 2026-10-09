from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment, Group
from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import AttendanceRecord, RecitationRecord, Schedule, SessionInstance
from .serializers import (
    GenerateSerializer,
    MarkSerializer,
    ScheduleSerializer,
    ScheduleWriteSerializer,
    SessionInstanceCreateSerializer,
    SessionInstanceRescheduleSerializer,
    SessionInstanceSerializer,
)
from .services import generate_planned_sessions, mark_attendance, mark_recitation

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]


def _as_drf_error(exc: DjangoValidationError):
    detail = exc.message if hasattr(exc, "message") else "; ".join(exc.messages)
    return serializers.ValidationError({"detail": detail})


class ScheduleListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = Schedule.objects.select_related("group")

    def get_queryset(self):
        qs = super().get_queryset()
        if group_id := self.request.query_params.get("group_id"):
            qs = qs.filter(group_id=group_id)
        return qs

    def get_serializer_class(self):
        return ScheduleWriteSerializer if self.request.method == "POST" else ScheduleSerializer


class ScheduleDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = Schedule.objects.select_related("group")

    def get_serializer_class(self):
        return ScheduleWriteSerializer if self.request.method in ("PUT", "PATCH") else ScheduleSerializer


class SessionInstanceListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = SessionInstance.objects.select_related("group")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if group_id := params.get("group_id"):
            qs = qs.filter(group_id=group_id)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        return qs

    def get_serializer_class(self):
        return SessionInstanceCreateSerializer if self.request.method == "POST" else SessionInstanceSerializer


class SessionGenerateView(APIView):
    """Expand the weekly schedules into PLANNED sessions (idempotent)."""

    permission_classes = IS_ENV_OWNER

    def post(self, request):
        ser = GenerateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        group = None
        if gid := ser.validated_data.get("group_id"):
            group = Group.objects.filter(id=gid, environment=request.environment).first()
            if not group:
                raise serializers.ValidationError({"group_id": "مجموعة غير موجودة."})
        created = generate_planned_sessions(request.environment, ser.validated_data["weeks"], group)
        return Response({"created": len(created)}, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


class SessionInstanceDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateAPIView):
    """PATCH only reschedules (`scheduled_at`), and only while still `planned`."""

    permission_classes = IS_ENV_OWNER
    queryset = SessionInstance.objects.select_related("group")

    def get_serializer_class(self):
        return SessionInstanceRescheduleSerializer if self.request.method in ("PUT", "PATCH") else SessionInstanceSerializer

    def perform_update(self, serializer):
        if serializer.instance.status != SessionInstance.Status.PLANNED:
            raise serializers.ValidationError({"detail": "لا يمكن تعديل موعد جلسة إلا وهي في حالة (مخطط لها)."})
        serializer.save()


class _SessionActionView(APIView):
    permission_classes = IS_ENV_OWNER
    action_method_name = None

    def post(self, request, pk):
        session = generics.get_object_or_404(SessionInstance.objects.filter(environment=request.environment), pk=pk)
        try:
            getattr(session, self.action_method_name)()
        except DjangoValidationError as e:
            raise _as_drf_error(e)
        return Response(SessionInstanceSerializer(session).data)


class SessionOpenView(_SessionActionView):
    action_method_name = "open"


class SessionCloseView(_SessionActionView):
    action_method_name = "close"


class SessionReopenView(_SessionActionView):
    action_method_name = "reopen"


class SessionRosterView(APIView):
    """Everything the Fast Session screen needs in ONE call: the active
    members of the session's group with their attendance + recitation mark
    (null = not marked yet). Tenant-scoped; the roster is the group's active
    enrollments only."""

    permission_classes = IS_ENV_OWNER

    def get(self, request, pk):
        session = generics.get_object_or_404(
            SessionInstance.objects.filter(environment=request.environment).select_related("group"), pk=pk
        )
        enrollments = list(
            Enrollment.objects.filter(
                environment=request.environment, is_active=True, groups=session.group_id
            ).select_related("student").order_by("student_name", "id")
        )
        att = dict(AttendanceRecord.objects.filter(session=session).values_list("enrollment_id", "status"))
        rec = dict(RecitationRecord.objects.filter(session=session).values_list("enrollment_id", "status"))
        return Response({
            "session": SessionInstanceSerializer(session).data,
            "students": [
                {"enrollment_id": e.id, "name": e.display_name, "attendance": att.get(e.id), "recitation": rec.get(e.id)}
                for e in enrollments
            ],
            "counts": {
                "total": len(enrollments),
                "present": sum(1 for v in att.values() if v == "present"),
                "absent": sum(1 for v in att.values() if v == "absent"),
                "studied": sum(1 for v in rec.values() if v == "studied"),
                "not_studied": sum(1 for v in rec.values() if v == "not_studied"),
            },
        })


class _MarkView(APIView):
    """One tap = one small atomic write (docs: per-tap persistence)."""

    permission_classes = IS_ENV_OWNER
    mark_fn = None

    def put(self, request):
        ser = MarkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        env = request.environment
        session = generics.get_object_or_404(
            SessionInstance.objects.filter(environment=env).select_related("group"), pk=v["session_id"]
        )
        enrollment = generics.get_object_or_404(Enrollment.objects.filter(environment=env), pk=v["enrollment_id"])
        try:
            record = type(self).mark_fn(session, enrollment, v["status"])
        except DjangoValidationError as e:
            raise _as_drf_error(e)
        return Response({"session_id": session.id, "enrollment_id": enrollment.id, "status": record.status})


class MarkAttendanceView(_MarkView):
    mark_fn = staticmethod(mark_attendance)


class MarkRecitationView(_MarkView):
    mark_fn = staticmethod(mark_recitation)
