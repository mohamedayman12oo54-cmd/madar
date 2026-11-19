"""Environments (a teacher's teaching space) as the team sees them.

Tenant isolation: this is the one place where the team reads across environments, deliberately. Every read of
one environment's private detail is authorised by `environments.view` and recorded in the audit log; there is no
endpoint that takes an environment id and returns ANOTHER environment's data under a different one. Student
names are shown only when the member also holds `students.view`; guardian contacts are never part of this view."""
from datetime import timedelta

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response

from academics.models import Enrollment, Grade, Group
from billing.models import Subscription
from environments.models import Environment
from evaluation.models import StudentState
from notifications.models import Notification
from scheduling.models import AttendanceRecord, Schedule, SessionInstance

from . import audit
from .access import HasControlPerm, can
from .common import ControlView, as_id, clean_search, invalid, iso, ordering, paginate
from .models import Ticket


def env_row(e, counts):
    c = counts.get(e.id, {})
    return {"id": e.id, "name": e.name, "subject_stage": e.subject_stage, "academic_year": e.academic_year,
            "owner": {"id": e.owner_id, "name": e.owner.name, "is_active": e.owner.is_active},
            "student_count": c.get("students", 0), "group_count": c.get("groups", 0),
            "created_at": iso(e.created_at), "status": "active" if e.owner.is_active else "suspended"}


class EnvironmentListView(ControlView):
    perm = "environments.view"

    def get(self, request):
        qs = Environment.objects.select_related("owner")
        if st := request.query_params.get("status"):
            qs = qs.filter(owner__is_active=(st == "active"))
        if s := clean_search(request):
            cond = Q(name__icontains=s) | Q(owner__name__icontains=s) | Q(subject_stage__icontains=s)
            if (eid := as_id(s)) is not None:
                cond |= Q(pk=eid)
            qs = qs.filter(cond)
        qs = qs.order_by(*ordering(request, {"name": "name", "created_at": "created_at", "id": "id"}, "-created_at"))
        page = paginate(request, qs, lambda e: e)
        envs = page["results"]
        ids = [e.id for e in envs]
        counts = {i: {} for i in ids}
        for env_id, n in Enrollment.objects.filter(environment_id__in=ids, is_active=True).values_list("environment_id").annotate(n=Count("id")):
            counts[env_id]["students"] = n
        for env_id, n in Group.objects.filter(environment_id__in=ids).values_list("environment_id").annotate(n=Count("id")):
            counts[env_id]["groups"] = n
        page["results"] = [env_row(e, counts) for e in envs]
        return Response(page)


class _EnvEdit(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    subject_stage = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_name(self, v):
        v = v.strip()
        if len(v) < 2:
            raise serializers.ValidationError("اسم البيئة يجب ألا يقل عن حرفين.")
        return v


def environment_detail(request, e):
    since = timezone.now() - timedelta(days=30)
    show_students = can(request, "students.view")
    enrollments = Enrollment.objects.filter(environment=e)
    attendance = dict(AttendanceRecord.objects.filter(environment=e, created_at__gte=since)
                      .values_list("status").annotate(n=Count("id")))
    states = dict(StudentState.objects.filter(environment=e, updated_at__gte=since).values_list("state").annotate(n=Count("id")))
    weekday = dict(Schedule.WEEKDAYS)
    sub = Subscription.objects.filter(environment=e).select_related("plan").first()
    d = {
        "id": e.id, "name": e.name, "subject_stage": e.subject_stage, "academic_year": e.academic_year,
        "created_at": iso(e.created_at),
        "owner": {"id": e.owner_id, "name": e.owner.name, "email": e.owner.email, "phone": e.owner.phone,
                  "is_active": e.owner.is_active},
        "counts": {"students_active": enrollments.filter(is_active=True).count(), "students_total": enrollments.count(),
                   "groups": Group.objects.filter(environment=e).count(), "grades": Grade.objects.filter(environment=e).count(),
                   "sessions_30d": SessionInstance.objects.filter(environment=e, scheduled_at__gte=since).count()},
        "grades": [{"id": g.id, "name": g.name, "students": enrollments.filter(grade=g, is_active=True).count()}
                   for g in Grade.objects.filter(environment=e)],
        "groups": [{"id": g.id, "name": g.name, "grade": g.grade.name, "students": g.member_enrollments.filter(is_active=True).count()}
                   for g in Group.objects.filter(environment=e).select_related("grade")],
        "schedules": [{"group": s.group.name, "weekday": weekday.get(s.weekday), "start": s.start_time.strftime("%H:%M"),
                       "end": s.end_time.strftime("%H:%M") if s.end_time else None}
                      for s in Schedule.objects.filter(environment=e).select_related("group")],
        "attendance_30d": {"present": attendance.get("present", 0), "absent": attendance.get("absent", 0)},
        "evaluations_30d": states,
        "recent_activity": [{"kind": "session", "text": f"جلسة {s.group.name} — {s.get_status_display()}", "at": iso(s.scheduled_at)}
                            for s in SessionInstance.objects.filter(environment=e).select_related("group").order_by("-scheduled_at")[:8]]
                           + [{"kind": "notification", "text": f"إشعار: {n.title}", "at": iso(n.created_at)}
                              for n in Notification.objects.filter(environment=e)[:5]],
        "subscription": {"state": sub.state, "plan": sub.plan.name if sub and sub.plan else None,
                         "period_end": iso(sub.current_period_end)} if sub else None,
        "tickets": [{"id": t.id, "number": t.number, "subject": t.subject, "status": t.status, "priority": t.priority}
                    for t in Ticket.objects.filter(environment=e)[:10]],
        "students": [],
    }
    if show_students:
        d["students"] = [{"id": en.student_id, "name": en.student_name or en.student.name, "grade": en.grade.name,
                          "is_active": en.is_active}
                         for en in enrollments.select_related("student", "grade").order_by("-created_at")[:100]]
    return d


class EnvironmentDetailView(ControlView):
    def get_permissions(self):
        return [HasControlPerm.require("environments.manage" if self.request.method == "PATCH" else "environments.view")()]

    def get(self, request, pk):
        e = get_object_or_404(Environment.objects.select_related("owner"), pk=pk)
        audit.record_view(request, "environment", e.id, e.name)
        return Response(environment_detail(request, e))

    def patch(self, request, pk):
        e = get_object_or_404(Environment.objects.select_related("owner"), pk=pk)
        ser = _EnvEdit(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        new = {k: (v.strip() if isinstance(v, str) else v) for k, v in ser.validated_data.items()}
        if not new:
            raise invalid(detail="لا توجد بيانات للتعديل.")
        old = {k: getattr(e, k) for k in new}
        before, after = audit.diff(old, new)
        if after:
            for k, v in new.items():
                setattr(e, k, v)
            e.save(update_fields=list(new))
            audit.record(request, "environment.update", "environment", e.id, e.name, before, after)
        return Response(environment_detail(request, e))
