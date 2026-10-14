from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Count, Q
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment, Grade, Group
from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import AttendanceRecord, GuestVisit, RecitationRecord, Schedule, SessionInstance
from .serializers import (
    BulkSessionSerializer,
    GenerateSerializer,
    MarkSerializer,
    ScheduleSerializer,
    ScheduleWriteSerializer,
    SessionInstanceCreateSerializer,
    SessionInstanceRescheduleSerializer,
    SessionInstanceSerializer,
)
from .services import (
    add_guest, close_due_sessions, generate_planned_sessions, mark_attendance, mark_guest, mark_recitation, remove_guest, set_home_session,
)

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
        # Sessions whose end time has passed close themselves (and record the
        # unmarked as absent) as soon as the teacher looks at the list.
        close_due_sessions(self.request.environment)
        qs = super().get_queryset()
        params = self.request.query_params
        if group_id := params.get("group_id"):
            qs = qs.filter(group_id=group_id)
        if grade_id := params.get("grade_id"):
            qs = qs.filter(group__grade_id=grade_id)
        if status_ := params.get("status"):
            qs = qs.filter(status=status_)
        return qs

    def get_serializer_class(self):
        return SessionInstanceCreateSerializer if self.request.method == "POST" else SessionInstanceSerializer


class SessionBulkCreateView(APIView):
    """One call -> one PLANNED session per selected group (all-or-nothing).

    Every id is checked against the caller's own environment. A group that
    already has a session at exactly that time is skipped, so pressing the
    button twice never doubles the lesson."""

    permission_classes = IS_ENV_OWNER

    def post(self, request):
        ser = BulkSessionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        env = request.environment
        groups = Group.objects.filter(environment=env)
        if grade_id := v.get("grade_id"):
            if not Grade.objects.filter(environment=env, id=grade_id).exists():
                raise serializers.ValidationError({"grade_id": "صف غير موجود."})
            groups = groups.filter(grade_id=grade_id)
        if ids := list(dict.fromkeys(v["group_ids"])):
            groups = groups.filter(id__in=ids)
            if groups.count() != len(ids):
                raise serializers.ValidationError({"group_ids": "مجموعة غير موجودة أو لا تتبع هذا الصف."})
        groups = list(groups.order_by("name"))
        if not groups:
            raise serializers.ValidationError({"detail": "لا توجد مجموعات في هذا الاختيار."})

        created, skipped = [], []
        with transaction.atomic():
            for g in groups:
                if SessionInstance.objects.filter(environment=env, group=g, scheduled_at=v["scheduled_at"]).exists():
                    skipped.append(g.name)
                    continue
                created.append(SessionInstance.objects.create(
                    environment=env, group=g, scheduled_at=v["scheduled_at"], ends_at=v.get("ends_at")))
        return Response(
            {"created": len(created), "skipped": skipped, "results": SessionInstanceSerializer(created, many=True).data},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


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


class SessionInstanceDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    """PATCH only reschedules (`scheduled_at`), and only while still `planned`.

    DELETE removes a session planned by mistake (wrong time, forgotten one).
    A session that already holds attendance / recitation / guest marks is
    refused: deleting it would silently erase those records."""

    permission_classes = IS_ENV_OWNER
    queryset = SessionInstance.objects.select_related("group")

    def get_serializer_class(self):
        return SessionInstanceRescheduleSerializer if self.request.method in ("PUT", "PATCH") else SessionInstanceSerializer

    def perform_update(self, serializer):
        if serializer.instance.status != SessionInstance.Status.PLANNED:
            raise serializers.ValidationError({"detail": "لا يمكن تعديل موعد جلسة إلا وهي في حالة (مخطط لها)."})
        serializer.save()

    def perform_destroy(self, instance):
        has_marks = (
            AttendanceRecord.objects.filter(session=instance).exists()
            or RecitationRecord.objects.filter(session=instance).exists()
            or GuestVisit.objects.filter(session=instance).exclude(attendance="", recitation="").exists()
        )
        if has_marks:
            raise serializers.ValidationError({
                "detail": "في هذه الجلسة تسجيلات حضور أو تسميع؛ لا يمكن حذفها حتى لا تضيع البيانات."})
        instance.delete()


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
        if session.is_overdue():
            session.close(auto=True)
        enrollments = list(
            Enrollment.objects.filter(
                environment=request.environment, is_active=True, groups=session.group_id
            ).select_related("student").order_by("student_name", "id")
        )
        att_rows = list(AttendanceRecord.objects.filter(session=session).values_list("enrollment_id", "status", "auto_marked"))
        att = {e: st for e, st, _ in att_rows}
        auto = {e for e, _, a in att_rows if a}
        rec = dict(RecitationRecord.objects.filter(session=session).values_list("enrollment_id", "status"))
        carried = {}
        for v in GuestVisit.objects.filter(home_session=session, applied_at__isnull=False).select_related("session__group"):
            carried[v.enrollment_id] = {"session_id": v.session_id, "scheduled_at": v.session.scheduled_at,
                                        "group": v.session.group.name}
        guests = GuestVisit.objects.filter(session=session).select_related(
            "enrollment__student", "home_session__group").order_by("created_at")
        return Response({
            "session": SessionInstanceSerializer(session).data,
            "students": [
                {"enrollment_id": e.id, "name": e.display_name, "attendance": att.get(e.id), "auto_absent": e.id in auto, "recitation": rec.get(e.id),
                 "carried_from": carried.get(e.id)}
                for e in enrollments
            ],
            "guests": [guest_row(v) for v in guests],
            "counts": {
                "total": len(enrollments),
                "present": sum(1 for v in att.values() if v == "present"),
                "absent": sum(1 for v in att.values() if v == "absent"),
                "auto_absent": len(auto),
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


# ------------------------------------------------------------ guest visits ----
def guest_row(v):
    home = v.home_session
    return {
        "enrollment_id": v.enrollment_id,
        "name": v.enrollment.display_name,
        "attendance": v.attendance or None,
        "recitation": v.recitation or None,
        "applied": v.applied_at is not None,
        "home_session": ({"id": home.id, "scheduled_at": home.scheduled_at, "group": home.group.name,
                          "status": home.status} if home else None),
    }


def _host_session(request, pk):
    return generics.get_object_or_404(
        SessionInstance.objects.filter(environment=request.environment).select_related("group"), pk=pk)


def _int(value, field):
    try:
        return int(value)
    except (TypeError, ValueError):
        raise serializers.ValidationError({field: "قيمة غير صحيحة."})


def _guest_enrollment(request, enrollment_id):
    enrollment_id = _int(enrollment_id, "enrollment_id")
    return generics.get_object_or_404(Enrollment.objects.filter(environment=request.environment), pk=enrollment_id)


def _home_or_none(request, home_id):
    if home_id in (None, ""):
        return None
    home_id = _int(home_id, "home_session_id")
    return generics.get_object_or_404(SessionInstance.objects.filter(environment=request.environment), pk=home_id)


class GuestCandidatesView(APIView):
    """Search students who are NOT in this session's group, to add as a guest.
    Each comes with his own upcoming sessions so the teacher can pick which one
    the visit replaces."""

    permission_classes = IS_ENV_OWNER

    def get(self, request, pk):
        host = _host_session(request, pk)
        q = (request.query_params.get("q") or "").replace("\x00", "").strip()
        qs = (Enrollment.objects.filter(environment=request.environment, is_active=True)
              .exclude(groups=host.group_id).exclude(guest_visits__session=host)
              .select_related("student", "grade").prefetch_related("groups"))
        if q:
            qs = qs.filter(Q(student_name__icontains=q) | Q(student__name__icontains=q))
        rows = []
        for e in qs.order_by("student_name", "id").distinct()[:20]:
            upcoming = (SessionInstance.objects
                        .filter(environment=request.environment, group__in=e.groups.all(),
                                status__in=["planned", "open"], scheduled_at__gt=host.scheduled_at)
                        .select_related("group").order_by("scheduled_at")[:4])
            rows.append({
                "enrollment_id": e.id, "name": e.display_name, "grade": e.grade.name,
                "groups": [g.name for g in e.groups.all()],
                "upcoming": [{"id": s.id, "scheduled_at": s.scheduled_at, "group": s.group.name, "status": s.status}
                             for s in upcoming],
            })
        return Response({"results": rows})


class GuestCreateView(APIView):
    permission_classes = IS_ENV_OWNER

    def post(self, request, pk):
        host = _host_session(request, pk)
        enrollment = _guest_enrollment(request, request.data.get("enrollment_id"))
        home = _home_or_none(request, request.data.get("home_session_id"))
        try:
            visit = add_guest(host, enrollment, home)
        except DjangoValidationError as e:
            raise _as_drf_error(e)
        visit = GuestVisit.objects.select_related("enrollment__student", "home_session__group").get(pk=visit.pk)
        return Response(guest_row(visit), status=status.HTTP_201_CREATED)


class GuestDetailView(APIView):
    """PUT {attendance?, recitation?, home_session_id?} marks one guest;
    DELETE cancels the visit while nothing has been carried over yet."""

    permission_classes = IS_ENV_OWNER

    def _visit(self, request, pk, enrollment_id):
        host = _host_session(request, pk)
        return host, generics.get_object_or_404(
            GuestVisit.objects.filter(session=host, enrollment_id=enrollment_id)
            .select_related("session__group", "enrollment__student", "home_session__group"))

    def put(self, request, pk, enrollment_id):
        host, visit = self._visit(request, pk, enrollment_id)
        try:
            if "home_session_id" in request.data:
                set_home_session(visit, _home_or_none(request, request.data.get("home_session_id")))
            for kind in ("attendance", "recitation"):
                if request.data.get(kind):
                    mark_guest(host, visit.enrollment, kind, request.data[kind])
        except DjangoValidationError as e:
            raise _as_drf_error(e)
        visit = GuestVisit.objects.select_related("enrollment__student", "home_session__group").get(pk=visit.pk)
        return Response(guest_row(visit))

    def delete(self, request, pk, enrollment_id):
        _, visit = self._visit(request, pk, enrollment_id)
        try:
            remove_guest(visit)
        except DjangoValidationError as e:
            raise _as_drf_error(e)
        return Response(status=status.HTTP_204_NO_CONTENT)
