from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import AttendanceRecord, SessionInstance
from .serializers import (
    AttendanceRecordSerializer,
    AttendanceUpdateSerializer,
    SessionInstanceCreateSerializer,
    SessionInstanceRescheduleSerializer,
    SessionInstanceSerializer,
)

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]


def _as_drf_error(exc: DjangoValidationError):
    detail = exc.message if hasattr(exc, "message") else "; ".join(exc.messages)
    return serializers.ValidationError({"detail": detail})


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


class SessionInstanceDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateAPIView):
    """PATCH only reschedules (`scheduled_at`), and only while still
    `planned` — enforced here since the serializer alone can't see the
    instance's current status before binding."""

    permission_classes = IS_ENV_OWNER
    queryset = SessionInstance.objects.select_related("group")

    def get_serializer_class(self):
        return SessionInstanceRescheduleSerializer if self.request.method in ("PUT", "PATCH") else SessionInstanceSerializer

    def perform_update(self, serializer):
        if serializer.instance.status != SessionInstance.Status.PLANNED:
            raise serializers.ValidationError({"detail": "لا يمكن تعديل موعد جلسة إلا وهي في حالة (مخطط لها)."})
        serializer.save()


class _SessionActionView(APIView):
    """Shared shape for open/close/reopen — see subclasses below."""

    permission_classes = IS_ENV_OWNER
    action_method_name = None

    def get_object(self, request, pk):
        return generics.get_object_or_404(
            SessionInstance.objects.filter(environment=request.environment), pk=pk
        )

    def post(self, request, pk):
        session = self.get_object(request, pk)
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


class AttendanceListView(TenantScopedQuerySetMixin, generics.ListAPIView):
    """No pagination override needed — StandardPagination applies globally;
    a single session's roster is small, and `?session_id=` scopes the common
    "mark this session's attendance" call to exactly that roster."""

    permission_classes = IS_ENV_OWNER
    serializer_class = AttendanceRecordSerializer
    queryset = AttendanceRecord.objects.select_related("enrollment__student", "session")

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if session_id := params.get("session_id"):
            qs = qs.filter(session_id=session_id)
        if enrollment_id := params.get("enrollment_id"):
            qs = qs.filter(enrollment_id=enrollment_id)
        if group_id := params.get("group_id"):
            qs = qs.filter(session__group_id=group_id)
        return qs


class AttendanceDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = AttendanceRecord.objects.select_related("enrollment__student", "session")

    def get_serializer_class(self):
        return AttendanceUpdateSerializer if self.request.method in ("PUT", "PATCH") else AttendanceRecordSerializer
