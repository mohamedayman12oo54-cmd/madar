"""Users, teachers, students and guardians as the team sees them. Everything here is READ from the existing
accounts / environments / academics models; the only writes are the audited edit / suspend / restore actions."""
from datetime import timedelta

from django.db import transaction
from django.db.models import Count, F, Max, Q
from django.db.models.functions import Greatest
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.response import Response

from academics.models import Enrollment, Group
from accounts.models import User
from accounts.phones import PhoneError, canonical_phone
from accounts.session_revocation import revoke_all_sessions
from ai.models import AIOperation
from environments.models import Environment, EnvironmentMembership
from notifications.models import Notification
from parents.models import GuardianMessage, GuardianReply
from scheduling.models import AttendanceRecord

from . import audit
from .access import can
from .common import ControlView, as_id, date_param, id_param, clean_search, invalid, iso, ordering, paginate
from .models import AuditLog, Ticket


# ------------------------------------------------------------------ status
def account_status(u):
    if not u.is_verified:
        return "pending"       # signed up / pre-registered, never confirmed by OTP
    return "active" if u.is_active else "suspended"


def with_activity(qs):
    return qs.annotate(last_activity=Greatest(F("last_login"), Max("memberships__last_accessed_at")))


def env_summary(env):
    return {"id": env.id, "name": env.name} if env else None


def user_environments(u):
    """The environments a user belongs to: a teacher owns one; a student may be enrolled in several."""
    if u.role == "teacher":
        env = Environment.objects.filter(owner=u).first()
        return [env_summary(env)] if env else []
    if u.role == "student":
        ids = u.enrollments.values_list("environment_id", flat=True)
        return [env_summary(e) for e in Environment.objects.filter(pk__in=ids)]
    return []


def user_row(u):
    return {
        "id": u.id, "name": u.name, "email": u.email, "phone": u.phone, "role": u.role,
        "status": account_status(u), "is_active": u.is_active, "is_verified": u.is_verified,
        "date_joined": iso(u.date_joined), "last_activity": iso(getattr(u, "last_activity", None) or u.last_login),
    }


def attach_environments(rows, users):
    """One query for the owners and one for the students instead of one per row."""
    teacher_ids = [u.id for u in users if u.role == "teacher"]
    student_ids = [u.id for u in users if u.role == "student"]
    by_user = {u.id: [] for u in users}
    for e in Environment.objects.filter(owner_id__in=teacher_ids):
        by_user[e.owner_id].append(env_summary(e))
    for en in Enrollment.objects.filter(student_id__in=student_ids).select_related("environment"):
        by_user[en.student_id].append(env_summary(en.environment))
    for row, u in zip(rows, users):
        row["environments"] = by_user[u.id]
        row["environment"] = (by_user[u.id] or [None])[0]
    return rows


def filtered_users(request, base):
    q = request.query_params
    qs = with_activity(base)
    if role := q.get("role"):
        qs = qs.filter(role=role)
    if st := q.get("status"):
        qs = {"pending": qs.filter(is_verified=False),
              "suspended": qs.filter(is_verified=True, is_active=False),
              "active": qs.filter(is_verified=True, is_active=True)}.get(st, qs)
    if (env := id_param(request, "environment")) is not None:
        qs = qs.filter(Q(owned_environment__pk=env) | Q(enrollments__environment_id=env)).distinct()
    for name, field in (("joined_from", "date_joined__date__gte"), ("joined_to", "date_joined__date__lte")):
        if (d := date_param(request, name)):
            qs = qs.filter(**{field: d})
    for name, op in (("active_from", "gte"), ("active_to", "lte")):
        if (d := date_param(request, name)):
            qs = qs.filter(**{f"last_activity__date__{op}": d})
    if s := clean_search(request):
        cond = Q(name__icontains=s) | Q(email__icontains=s) | Q(phone__icontains=s)
        if (uid := as_id(s)) is not None:
            cond |= Q(pk=uid)
        qs = qs.filter(cond)
    return qs.order_by(*ordering(request, {
        "name": "name", "date_joined": "date_joined", "last_activity": "last_activity", "id": "id"}, "-date_joined"))


def list_response(request, base, extra=None):
    qs = filtered_users(request, base)
    page = paginate(request, qs, lambda u: u)
    users = page["results"]
    rows = attach_environments([user_row(u) for u in users], users)
    if extra:
        extra(rows, users)
    page["results"] = rows
    return Response(page)


# ------------------------------------------------------------------ views
class UserListView(ControlView):
    perm = "users.view"

    def get(self, request):
        return list_response(request, User.objects.exclude(role="team"))


class TeacherListView(ControlView):
    perm = "teachers.view"

    def get(self, request):
        def extra(rows, users):
            ids = [u.id for u in users]
            students = dict(Enrollment.objects.filter(environment__owner_id__in=ids, is_active=True)
                            .values_list("environment__owner_id").annotate(n=Count("id")))
            groups = dict(Group.objects.filter(environment__owner_id__in=ids)
                          .values_list("environment__owner_id").annotate(n=Count("id")))
            for r in rows:
                r["student_count"] = students.get(r["id"], 0)
                r["group_count"] = groups.get(r["id"], 0)

        return list_response(request, User.objects.filter(role="teacher"), extra)


class StudentListView(ControlView):
    perm = "students.view"

    def get(self, request):
        def extra(rows, users):
            enr = {}
            for e in Enrollment.objects.filter(student_id__in=[u.id for u in users]).select_related("environment__owner", "grade"):
                enr.setdefault(e.student_id, []).append(e)
            for r in rows:
                es = enr.get(r["id"], [])
                r["enrollments"] = [{"environment_id": e.environment_id, "teacher": e.environment.owner.name,
                                     "grade": e.grade.name, "is_active": e.is_active} for e in es]
                r["active_enrollments"] = sum(1 for e in es if e.is_active)

        return list_response(request, User.objects.filter(role="student"), extra)


# ------------------------------------------------------------------ detail
def user_detail(request, u):
    d = user_row(u)
    d["environments"] = user_environments(u)
    d["last_login"] = iso(u.last_login)
    d["session_version"] = u.session_version
    d["open_tickets"] = Ticket.objects.filter(requester=u, status__in=Ticket.ACTIVE).count()
    d["total_tickets"] = Ticket.objects.filter(requester=u).count()
    d["notifications_count"] = Notification.objects.filter(recipient=u).count()
    d["ai_operations_count"] = AIOperation.objects.filter(requested_by=u).count()
    if u.role == "teacher":
        env = Environment.objects.filter(owner=u).first()
        if env:
            d["teacher"] = {
                "environment": {"id": env.id, "name": env.name, "subject_stage": env.subject_stage,
                                "academic_year": env.academic_year, "created_at": iso(env.created_at)},
                "students_active": Enrollment.objects.filter(environment=env, is_active=True).count(),
                "students_total": Enrollment.objects.filter(environment=env).count(),
                "groups": Group.objects.filter(environment=env).count(),
                "schedules": _count("scheduling.Schedule", env),
                "attendance_records_30d": AttendanceRecord.objects.filter(
                    environment=env, created_at__gte=timezone.now() - timedelta(days=30)).count(),
                "evaluations_30d": _count("evaluation.StudentState", env, days=30),
                "sessions_30d": _count("scheduling.SessionInstance", env, days=30),
            }
    if u.role == "student":
        d["student"] = [{
            "environment": {"id": e.environment_id, "name": e.environment.name},
            "teacher": e.environment.owner.name, "grade": e.grade.name, "academic_year": e.academic_year,
            "is_active": e.is_active, "enrolled_at": iso(e.created_at),
            "groups": [g.name for g in e.groups.all()],
            "attendance": dict(AttendanceRecord.objects.filter(enrollment=e).values_list("status").annotate(n=Count("id"))),
            "ratings": list(e.monthly_ratings.filter(published_at__isnull=False).values("month", "value")[:6]),
            "states": [{"month": s.month.isoformat(), "state": s.state} for s in e.monthly_states.all()[:6]],
            # Guardian relationship: shown only to a member who may see guardians at all.
            **({"guardian": {"name": e.parent_name, "phone": e.parent_phone}} if can(request, "parents.view") else {}),
        } for e in u.enrollments.select_related("environment__owner", "grade").prefetch_related("groups")]
    return d


def _count(model_label, env, days=None):
    from django.apps import apps

    qs = apps.get_model(model_label).objects.filter(environment=env)
    if days:
        field = "scheduled_at" if model_label.endswith("SessionInstance") else "updated_at"
        qs = qs.filter(**{f"{field}__gte": timezone.now() - timedelta(days=days)})
    return qs.count()


def _user_or_404(pk, roles=("teacher", "student")):
    return get_object_or_404(User.objects.filter(role__in=roles), pk=pk)


EDITABLE = ("name", "email", "phone")


class UserEditSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    email = serializers.EmailField(required=False, allow_blank=True, allow_null=True)
    phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)

    def validate_name(self, v):
        v = v.strip()
        if len(v) < 2:
            raise serializers.ValidationError("الاسم يجب ألا يقل عن حرفين.")
        return v

    def validate_email(self, v):
        return (v or "").strip().lower() or None

    def validate_phone(self, v):
        if not v:
            return None
        try:
            return canonical_phone(v)
        except PhoneError as exc:
            raise serializers.ValidationError(exc.message_ar)


class UserDetailView(ControlView):
    """GET needs the role-matching view permission; PATCH needs users.edit."""

    def get_permissions(self):
        from .access import HasControlPerm

        return [HasControlPerm.require("users.edit" if self.request.method == "PATCH" else "users.view")()]

    def get(self, request, pk):
        u = _user_or_404(pk)
        _require_role_view(request, u)
        audit.record_view(request, "user", u.id, u.name)
        return Response(user_detail(request, u))

    def patch(self, request, pk):
        u = _user_or_404(pk)
        ser = UserEditSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        new = ser.validated_data
        if not new:
            raise invalid(detail="لا توجد بيانات للتعديل.")
        errors = {}
        if "email" in new and new["email"] and User.objects.filter(email__iexact=new["email"]).exclude(pk=u.pk).exists():
            errors["email"] = ["هذا البريد الإلكتروني مستخدم بالفعل."]
        if "phone" in new and new["phone"] and User.objects.filter(phone=new["phone"]).exclude(pk=u.pk).exists():
            errors["phone"] = ["رقم الهاتف هذا مستخدم بالفعل."]
        if errors:
            raise serializers.ValidationError(errors)
        old = {k: getattr(u, k) for k in new}
        if all(old[k] == new[k] for k in new):
            return Response(user_detail(request, u))
        with transaction.atomic():
            for k, v in new.items():
                setattr(u, k, v)
            u.save(update_fields=list(new))
            before, after = audit.diff(old, new)
            audit.record(request, "user.update", "user", u.id, u.name, before, after)
        return Response(user_detail(request, u))


def _require_role_view(request, u):
    from rest_framework.exceptions import PermissionDenied

    need = {"teacher": "teachers.view", "student": "students.view"}.get(u.role, "users.view")
    if not (can(request, need) or can(request, "users.view")):
        raise PermissionDenied("ليس لديك صلاحية عرض هذا المستخدم.")


class _ReasonSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")


class UserSuspendView(ControlView):
    perm = "users.suspend"

    def post(self, request, pk):
        ser = _ReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            u = get_object_or_404(User.objects.select_for_update().filter(role__in=("teacher", "student")), pk=pk)
            if not u.is_verified:
                raise invalid(detail="الحساب لم يكتمل تفعيله بعد، ولا يمكن إيقافه.")
            if not u.is_active:
                raise invalid(detail="الحساب موقوف بالفعل.")
            u.is_active = False
            u.save(update_fields=["is_active"])
            revoke_all_sessions(u)  # takes effect now, not when the access token expires
            audit.record(request, "user.suspend", "user", u.id, u.name, {"status": "active"}, {"status": "suspended"},
                         note=ser.validated_data["reason"])
        return Response(user_detail(request, u))


class UserRestoreView(ControlView):
    perm = "users.suspend"

    def post(self, request, pk):
        ser = _ReasonSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            u = get_object_or_404(User.objects.select_for_update().filter(role__in=("teacher", "student")), pk=pk)
            if u.is_active or not u.is_verified:
                raise invalid(detail="الحساب غير موقوف.")
            u.is_active = True
            u.save(update_fields=["is_active"])
            audit.record(request, "user.restore", "user", u.id, u.name, {"status": "suspended"}, {"status": "active"},
                         note=ser.validated_data["reason"])
        return Response(user_detail(request, u))


class UserActivityView(ControlView):
    perm = "users.view"

    def get(self, request, pk):
        u = _user_or_404(pk)
        items = []
        for m in EnvironmentMembership.objects.filter(user=u, last_accessed_at__isnull=False).select_related("environment"):
            items.append({"kind": "env_access", "text": f"دخل بيئة «{m.environment.name}»", "at": m.last_accessed_at})
        if u.last_login:
            items.append({"kind": "login", "text": "تسجيل دخول", "at": u.last_login})
        for op in AIOperation.objects.filter(requested_by=u)[:15]:
            items.append({"kind": "ai", "text": f"عملية ذكاء اصطناعي ({op.get_kind_display()}) — {op.get_status_display()}",
                          "at": op.created_at})
        for t in Ticket.objects.filter(requester=u)[:15]:
            items.append({"kind": "ticket", "text": f"تذكرة {t.number}: {t.subject}", "at": t.created_at, "ticket_id": t.id})
        for n in Notification.objects.filter(recipient=u)[:15]:
            items.append({"kind": "notification", "text": f"إشعار: {n.title}", "at": n.created_at})
        if u.role == "student":
            for r in AttendanceRecord.objects.filter(enrollment__student=u).order_by("-created_at")[:15]:
                items.append({"kind": "attendance", "text": f"سُجّل {r.get_status_display()}", "at": r.created_at})
        items.sort(key=lambda i: i["at"], reverse=True)
        return Response([{**i, "at": iso(i["at"])} for i in items[:50]])


class UserTicketsView(ControlView):
    perm = "tickets.view"

    def get(self, request, pk):
        u = _user_or_404(pk)
        from .support import ticket_row

        return Response([ticket_row(t) for t in Ticket.objects.filter(requester=u).select_related("category", "assignee")[:50]])


class UserNotificationsView(ControlView):
    perm = ("notifications.view", "users.view")

    def get(self, request, pk):
        u = _user_or_404(pk)
        return Response([{
            "id": n.id, "type": n.type, "type_label": n.get_type_display(), "title": n.title,
            "delivery_status": n.delivery_status, "delivery_error": n.delivery_error,
            "created_at": iso(n.created_at), "delivered_at": iso(n.delivered_at), "read_at": iso(n.read_at),
        } for n in Notification.objects.filter(recipient=u)[:50]])


class UserHistoryView(ControlView):
    perm = "audit.view"

    def get(self, request, pk):
        u = _user_or_404(pk)
        return Response([audit_row(a) for a in AuditLog.objects.filter(entity_type="user", entity_id=str(u.id))[:50]])


def audit_row(a):
    return {"id": a.id, "actor": a.actor_label, "actor_id": a.actor_id, "action": a.action, "entity_type": a.entity_type,
            "entity_id": a.entity_id, "entity_label": a.entity_label, "before": a.before, "after": a.after,
            "note": a.note, "ip_address": a.ip_address, "created_at": iso(a.created_at)}


# ------------------------------------------------------------------ guardians
def _guardian_groups(search=""):
    qs = Enrollment.objects.exclude(parent_phone="").select_related("student", "environment__owner", "grade")
    if search:
        qs = qs.filter(Q(parent_phone__icontains=search) | Q(parent_name__icontains=search)
                       | Q(student_name__icontains=search) | Q(student__name__icontains=search))
    groups = {}
    for e in qs.order_by("-created_at"):
        groups.setdefault(e.parent_phone, []).append(e)
    return groups


def access_issues(e):
    """Why this guardian could not open the portal for this child right now — derived from the real rules in
    parents/auth.py (child's account must be claimed and active), never guessed."""
    issues = []
    if not e.is_active:
        issues.append("تسجيل الطالب غير نشط لدى المعلّم")
    if not e.student.is_verified:
        issues.append("الطالب لم يفعّل حسابه بعد")
    if not e.student.is_active:
        issues.append("حساب الطالب موقوف")
    return issues


class ParentListView(ControlView):
    perm = "parents.view"

    def get(self, request):
        groups = _guardian_groups(clean_search(request))
        only_issues = request.query_params.get("issues") == "1"
        rows = []
        phones = list(groups)
        unread = dict(GuardianMessage.objects.filter(enrollment__parent_phone__in=phones, read_at__isnull=True)
                      .values_list("enrollment__parent_phone").annotate(n=Count("id")))
        for phone, es in groups.items():
            issues = [i for e in es for i in access_issues(e)]
            if only_issues and not issues:
                continue
            rows.append({"phone": phone, "name": next((e.parent_name for e in es if e.parent_name), ""),
                         "children": len(es), "environments": sorted({e.environment.name for e in es}),
                         "unread_messages": unread.get(phone, 0), "has_access_issues": bool(issues)})
        rows.sort(key=lambda r: (not r["has_access_issues"], r["phone"]))
        page = as_id(request.query_params.get("page", "1") or "1") or 1
        size = 20
        return Response({"count": len(rows), "page": page, "page_size": size, "pages": max((len(rows) + size - 1) // size, 1),
                         "results": rows[(page - 1) * size: page * size]})


class ParentDetailView(ControlView):
    perm = "parents.view"

    def get(self, request, phone):
        if not (phone.isascii() and phone.isdigit() and len(phone) <= 20):
            raise invalid(phone="رقم غير صالح.")
        es = list(Enrollment.objects.filter(parent_phone=phone).select_related("student", "environment__owner", "grade"))
        if not es:
            return Response({"detail": "لا يوجد ولي أمر بهذا الرقم.", "code": "not_found"}, status=404)
        audit.record_view(request, "guardian", phone, phone)
        ids = [e.id for e in es]
        msgs = GuardianMessage.objects.filter(enrollment_id__in=ids).select_related("enrollment__student", "sent_by")[:40]
        replies = GuardianReply.objects.filter(enrollment_id__in=ids).select_related("enrollment__student")[:40]
        return Response({
            "phone": phone, "name": next((e.parent_name for e in es if e.parent_name), ""),
            "children": [{
                "enrollment_id": e.id, "student": e.student_name or e.student.name, "environment": e.environment.name,
                "teacher": e.environment.owner.name, "grade": e.grade.name, "enrollment_active": e.is_active,
                "student_claimed": e.student.is_verified, "access_ready": not access_issues(e),
                "issues": access_issues(e),
            } for e in es],
            "messages": [{
                "id": m.id, "kind": m.kind, "title": m.title, "body": m.body[:300], "automatic": m.automatic,
                "student": m.enrollment.student_name or m.enrollment.student.name, "sent_by": m.sent_by.name if m.sent_by else "النظام",
                "read_at": iso(m.read_at), "created_at": iso(m.created_at),
            } for m in msgs],
            "replies": [{"id": r.id, "student": r.enrollment.student_name or r.enrollment.student.name,
                         "body": r.body[:300], "created_at": iso(r.created_at), "read_by_teacher": bool(r.read_at)}
                        for r in replies],
            "tickets": [t for t in _guardian_tickets(phone)],
        })


def _guardian_tickets(phone):
    from .support import ticket_row

    return [ticket_row(t) for t in Ticket.objects.filter(requester_phone=phone).select_related("category", "assignee")[:20]]
