"""Reports. Every report is computed from the live tables for a date range (and optional environment / status /
user-type filters) and can be downloaded as CSV; PDF is produced by the browser's print dialog on the report page.

Privacy: a report only lists NAMED people when the member also holds the matching view permission
(`users.view`, `teachers.view`, ...). Without it the report is aggregated (counts per day / per category) — an
analyst can study trends without ever seeing a person."""
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from rest_framework.response import Response

from academics.models import Enrollment, Group
from accounts.models import User
from ai.models import AIOperation
from billing.models import PaymentAttempt
from environments.models import Environment
from notifications.models import Notification

from .access import can
from .common import ControlView, id_param, csv_response, day_list, invalid, iso, parse_range, series
from .models import AuditLog, Ticket
from .support import DUR as FIRST_RESPONSE, RES as RESOLUTION
from .users import account_status, with_activity

REPORTS = {
    "users": "تقرير المستخدمين", "teachers": "تقرير المعلّمين", "students": "تقرير الطلاب", "environments": "تقرير البيئات",
    "tickets": "تقرير تذاكر الدعم", "agents": "أداء فريق الدعم", "finance": "تقرير العمليات المالية",
    "ai": "تقرير الذكاء الاصطناعي", "notifications": "تقرير الإشعارات", "admin_activity": "تقرير النشاط الإداري",
}
# (the aggregated report is allowed with `reports.view`; the permission below unlocks the named detail table)
DETAIL_PERM = {"teachers": "teachers.view", "students": "students.view", "environments": "environments.view",
               "tickets": "tickets.view", "finance": "finance.view", "users": "users.view"}
# a few reports expose data of their own domain and need that domain's permission even in aggregate
DOMAIN_PERM = {"agents": "support.analytics", "admin_activity": "audit.view", "finance": "finance.view", "ai": "ai.view",
               "notifications": "notifications.view"}


def cols(*pairs):
    return [{"key": k, "label": l} for k, l in pairs]


def merge_days(start, end, **named):
    """named: {key: series} -> rows [{date, key: value, ...}] aligned by day."""
    rows = []
    for i, d in enumerate(day_list(start, end)):
        row = {"date": d.isoformat()}
        for key, ser in named.items():
            row[key] = ser[i]["value"]
        rows.append(row)
    return rows


def person_qs(request, role=None):
    qs = User.objects.exclude(role="team")
    if role:
        qs = qs.filter(role=role)
    elif request.query_params.get("role") in ("teacher", "student"):
        qs = qs.filter(role=request.query_params["role"])
    env = id_param(request, "environment")
    if env is not None:
        qs = qs.filter(Q(owned_environment__pk=env) | Q(enrollments__environment_id=env)).distinct()
    return qs


def report_users(request, start, end, role=None):
    qs = person_qs(request, role)
    base = qs.filter(date_joined__gte=start, date_joined__lt=end)
    status = request.query_params.get("status")
    if status:
        base = {"pending": base.filter(is_verified=False), "suspended": base.filter(is_verified=True, is_active=False),
                "active": base.filter(is_verified=True, is_active=True)}.get(status, base)
    t, s = base.filter(role="teacher"), base.filter(role="student")
    out = {
        "columns": cols(("date", "التاريخ"), ("teachers", "معلّمون جدد"), ("students", "طلاب جدد"), ("total", "الإجمالي")),
        "rows": [{**r, "total": r["teachers"] + r["students"]} for r in
                 merge_days(start, end, teachers=series(t, "date_joined", start, end), students=series(s, "date_joined", start, end))],
        "totals": {"new": base.count(), "all": qs.count(),
                   "active": qs.filter(is_verified=True, is_active=True).count(),
                   "suspended": qs.filter(is_verified=True, is_active=False).count(),
                   "pending": qs.filter(is_verified=False).count()},
        "breakdowns": [{"title": "حسب الحالة", "columns": cols(("name", "الحالة"), ("count", "العدد")), "rows": [
            {"name": "نشط", "count": qs.filter(is_verified=True, is_active=True).count()},
            {"name": "موقوف", "count": qs.filter(is_verified=True, is_active=False).count()},
            {"name": "بانتظار التفعيل", "count": qs.filter(is_verified=False).count()}]}],
    }
    if can(request, "users.view") and role is None:
        out["detail"] = {"title": "قائمة المستخدمين", "columns": cols(("id", "المعرّف"), ("name", "الاسم"), ("role", "النوع"), ("status", "الحالة"), ("joined", "تاريخ التسجيل")),
                         "rows": [{"id": u.id, "name": u.name, "role": u.role, "status": account_status(u), "joined": iso(u.date_joined)}
                                  for u in with_activity(base).order_by("-date_joined")[:2000]]}
    return out


def report_teachers(request, start, end):
    out = report_users(request, start, end, role="teacher")
    out["columns"] = cols(("date", "التاريخ"), ("teachers", "معلّمون جدد"))
    out["rows"] = [{"date": r["date"], "teachers": r["teachers"]} for r in out["rows"]]
    if can(request, "teachers.view"):
        envs = Environment.objects.select_related("owner").order_by("-created_at")[:2000]
        stu = dict(Enrollment.objects.filter(is_active=True).values_list("environment_id").annotate(n=Count("id")))
        grp = dict(Group.objects.values_list("environment_id").annotate(n=Count("id")))
        out["detail"] = {"title": "المعلّمون وبيئاتهم", "columns": cols(("name", "المعلّم"), ("environment", "البيئة"), ("students", "الطلاب النشطون"), ("groups", "المجموعات"), ("status", "الحالة")),
                         "rows": [{"name": e.owner.name, "environment": e.name, "students": stu.get(e.id, 0), "groups": grp.get(e.id, 0),
                                   "status": account_status(e.owner)} for e in envs]}
    return out


def report_students(request, start, end):
    out = report_users(request, start, end, role="student")
    out["columns"] = cols(("date", "التاريخ"), ("students", "طلاب جدد"))
    out["rows"] = [{"date": r["date"], "students": r["students"]} for r in out["rows"]]
    en = Enrollment.objects.all()
    if (_env := id_param(request, "environment")) is not None:
        en = en.filter(environment_id=_env)
    out["breakdowns"].append({"title": "التسجيلات", "columns": cols(("name", "الحالة"), ("count", "العدد")), "rows": [
        {"name": "نشط لدى المعلّم", "count": en.filter(is_active=True).count()}, {"name": "غير نشط", "count": en.filter(is_active=False).count()}]})
    if can(request, "students.view"):
        out["detail"] = {"title": "الطلاب", "columns": cols(("name", "الطالب"), ("teacher", "المعلّم"), ("grade", "الصف"), ("active", "نشط"), ("enrolled", "تاريخ التسجيل")),
                         "rows": [{"name": e.student_name or e.student.name, "teacher": e.environment.owner.name, "grade": e.grade.name,
                                   "active": "نعم" if e.is_active else "لا", "enrolled": iso(e.created_at)}
                                  for e in en.select_related("student", "environment__owner", "grade").order_by("-created_at")[:2000]]}
    return out


def report_environments(request, start, end):
    envs = Environment.objects.all()
    new = envs.filter(created_at__gte=start, created_at__lt=end)
    out = {"columns": cols(("date", "التاريخ"), ("created", "بيئات جديدة")),
           "rows": merge_days(start, end, created=series(envs, "created_at", start, end)),
           "totals": {"new": new.count(), "all": envs.count(), "with_students": Enrollment.objects.values("environment").distinct().count()},
           "breakdowns": []}
    if can(request, "environments.view"):
        stu = dict(Enrollment.objects.filter(is_active=True).values_list("environment_id").annotate(n=Count("id")))
        grp = dict(Group.objects.values_list("environment_id").annotate(n=Count("id")))
        out["detail"] = {"title": "البيئات", "columns": cols(("id", "المعرّف"), ("name", "البيئة"), ("owner", "المالك"), ("students", "الطلاب"), ("groups", "المجموعات"), ("created", "تاريخ الإنشاء")),
                         "rows": [{"id": e.id, "name": e.name, "owner": e.owner.name, "students": stu.get(e.id, 0), "groups": grp.get(e.id, 0),
                                   "created": iso(e.created_at)} for e in envs.select_related("owner").order_by("-created_at")[:2000]]}
    return out


def ticket_filters(request, qs):
    q = request.query_params
    if q.get("status"):
        qs = qs.filter(status=q["status"])
    if q.get("role") in ("teacher", "student", "parent", "other"):
        qs = qs.filter(requester_kind=q["role"])
    if (_environment := id_param(request, "environment")) is not None:
        qs = qs.filter(environment_id=_environment)
    return qs


def report_tickets(request, start, end):
    allq = ticket_filters(request, Ticket.objects.all())
    created = allq.filter(created_at__gte=start, created_at__lt=end)
    done = allq.filter(resolved_at__gte=start, resolved_at__lt=end)
    out = {"columns": cols(("date", "التاريخ"), ("created", "تذاكر جديدة"), ("resolved", "تذاكر محلولة")),
           "rows": merge_days(start, end, created=series(allq, "created_at", start, end), resolved=series(allq, "resolved_at", start, end)),
           "totals": {"created": created.count(), "resolved": done.count(),
                      "avg_first_response_hours": _h(created.filter(first_response_at__isnull=False).aggregate(v=Avg(FIRST_RESPONSE))["v"]),
                      "avg_resolution_hours": _h(done.aggregate(v=Avg(RESOLUTION))["v"])},
           "breakdowns": [
               {"title": "حسب التصنيف", "columns": cols(("name", "التصنيف"), ("count", "العدد")),
                "rows": list(created.values(name=F("category__name")).annotate(count=Count("id")).order_by("-count"))},
               {"title": "حسب الأولوية", "columns": cols(("name", "الأولوية"), ("count", "العدد")),
                "rows": [{"name": dict(Ticket.Priority.choices)[p], "count": n} for p, n in created.values_list("priority").annotate(n=Count("id"))]},
               {"title": "حسب الحالة", "columns": cols(("name", "الحالة"), ("count", "العدد")),
                "rows": [{"name": dict(Ticket.Status.choices)[s], "count": n} for s, n in created.values_list("status").annotate(n=Count("id"))]}]}
    if can(request, "tickets.view"):
        out["detail"] = {"title": "التذاكر", "columns": cols(("number", "الرقم"), ("subject", "العنوان"), ("status", "الحالة"), ("priority", "الأولوية"), ("category", "التصنيف"), ("created", "التاريخ")),
                         "rows": [{"number": t.number, "subject": t.subject, "status": t.get_status_display(), "priority": t.get_priority_display(),
                                   "category": t.category.name, "created": iso(t.created_at)}
                                  for t in created.select_related("category").order_by("-created_at")[:2000]]}
    return out


def _h(d):
    return round(d.total_seconds() / 3600, 2) if d is not None else None


def report_agents(request, start, end):
    rows = (Ticket.objects.filter(assignee__isnull=False, created_at__gte=start, created_at__lt=end)
            .values("assignee__name").annotate(assigned=Count("id"), resolved=Count("id", filter=Q(status__in=("resolved", "closed"))),
                                               rating=Avg("rating"), resp=Avg(FIRST_RESPONSE)).order_by("-assigned"))
    return {"columns": cols(("agent", "الموظف"), ("assigned", "المسندة"), ("resolved", "المحلولة"), ("avg_response_hours", "متوسط أول رد (ساعة)"), ("avg_rating", "متوسط التقييم")),
            "rows": [{"agent": r["assignee__name"], "assigned": r["assigned"], "resolved": r["resolved"],
                      "avg_response_hours": _h(r["resp"]), "avg_rating": round(r["rating"], 2) if r["rating"] else None} for r in rows],
            "totals": {"agents": len(rows)}, "breakdowns": []}


def report_finance(request, start, end):
    q = request.query_params
    qs = PaymentAttempt.objects.all()
    if (_environment := id_param(request, "environment")) is not None:
        qs = qs.filter(environment_id=_environment)
    if q.get("status"):
        qs = qs.filter(status=q["status"])
    rng = qs.filter(created_at__gte=start, created_at__lt=end)
    ok = qs.filter(status="succeeded")
    from .business import _revenue_series  # same daily revenue as the finance dashboard

    revenue = _revenue_series(start, end)
    out = {"columns": cols(("date", "التاريخ"), ("succeeded", "ناجحة"), ("failed", "فاشلة"), ("revenue", "الإيراد")),
           "rows": merge_days(start, end, succeeded=series(ok, "created_at", start, end),
                              failed=series(qs.filter(status="failed"), "created_at", start, end), revenue=revenue),
           "totals": {"transactions": rng.count(), "succeeded": rng.filter(status="succeeded").count(), "failed": rng.filter(status="failed").count(),
                      "revenue": (rng.filter(status="succeeded").aggregate(s=Sum("amount_minor_units"))["s"] or 0) / 100},
           "breakdowns": [{"title": "حسب الحالة", "columns": cols(("name", "الحالة"), ("count", "العدد")),
                           "rows": [{"name": dict(PaymentAttempt.Status.choices)[s], "count": n} for s, n in rng.values_list("status").annotate(n=Count("id"))]}]}
    out["detail"] = {"title": "المعاملات", "columns": cols(("id", "المعاملة"), ("environment", "البيئة"), ("amount", "المبلغ"), ("currency", "العملة"), ("status", "الحالة"), ("created", "التاريخ")),
                     "rows": [{"id": a.merchant_order_id, "environment": a.environment.name, "amount": a.amount_minor_units / 100, "currency": a.currency,
                               "status": a.get_status_display(), "created": iso(a.created_at)}
                              for a in rng.select_related("environment").order_by("-created_at")[:2000]]}
    return out


def report_ai(request, start, end):
    q = request.query_params
    qs = AIOperation.objects.all()
    if (_environment := id_param(request, "environment")) is not None:
        qs = qs.filter(environment_id=_environment)
    if q.get("status"):
        qs = qs.filter(status=q["status"])
    rng = qs.filter(created_at__gte=start, created_at__lt=end)
    dur = ExpressionWrapper(F("completed_at") - F("started_at"), output_field=DurationField())
    cats = {}
    for md in rng.filter(status="failed").values_list("metadata", flat=True):
        c = (md or {}).get("failure_category") or "unknown"
        cats[c] = cats.get(c, 0) + 1
    return {"columns": cols(("date", "التاريخ"), ("completed", "ناجحة"), ("failed", "فاشلة")),
            "rows": merge_days(start, end, completed=series(qs.filter(status="completed"), "created_at", start, end),
                               failed=series(qs.filter(status="failed"), "created_at", start, end)),
            "totals": {"total": rng.count(), "completed": rng.filter(status="completed").count(), "failed": rng.filter(status="failed").count(),
                       "avg_seconds": (lambda d: round(d.total_seconds(), 2) if d else None)(rng.filter(completed_at__isnull=False, started_at__isnull=False).aggregate(v=Avg(dur))["v"])},
            "breakdowns": [{"title": "حسب النوع", "columns": cols(("name", "النوع"), ("count", "العدد")),
                            "rows": [{"name": dict(AIOperation.Kind.choices).get(k, k), "count": n} for k, n in rng.values_list("kind").annotate(n=Count("id"))]},
                           {"title": "أسباب الفشل", "columns": cols(("name", "السبب"), ("count", "العدد")),
                            "rows": [{"name": c, "count": n} for c, n in sorted(cats.items(), key=lambda x: -x[1])]}]}


def report_notifications(request, start, end):
    q = request.query_params
    qs = Notification.objects.all()
    if (_environment := id_param(request, "environment")) is not None:
        qs = qs.filter(environment_id=_environment)
    if q.get("status"):
        qs = qs.filter(delivery_status=q["status"])
    rng = qs.filter(created_at__gte=start, created_at__lt=end)
    return {"columns": cols(("date", "التاريخ"), ("sent", "مُرسلة"), ("failed", "فاشلة"), ("pending", "قيد الإرسال")),
            "rows": merge_days(start, end, sent=series(qs.filter(delivery_status="sent"), "created_at", start, end),
                               failed=series(qs.filter(delivery_status="failed"), "created_at", start, end),
                               pending=series(qs.filter(delivery_status="pending"), "created_at", start, end)),
            "totals": {"total": rng.count(), "sent": rng.filter(delivery_status="sent").count(), "failed": rng.filter(delivery_status="failed").count(),
                       "read": rng.filter(read_at__isnull=False).count()},
            "breakdowns": [{"title": "حسب النوع", "columns": cols(("name", "النوع"), ("count", "العدد")),
                            "rows": [{"name": dict(Notification.Type.choices).get(t, t), "count": n} for t, n in rng.values_list("type").annotate(n=Count("id"))]}]}


def report_admin_activity(request, start, end):
    qs = AuditLog.objects.exclude(action="view")
    rng = qs.filter(created_at__gte=start, created_at__lt=end)
    return {"columns": cols(("date", "التاريخ"), ("actions", "الإجراءات")),
            "rows": merge_days(start, end, actions=series(qs, "created_at", start, end)),
            "totals": {"actions": rng.count()},
            "breakdowns": [{"title": "حسب الإجراء", "columns": cols(("name", "الإجراء"), ("count", "العدد")),
                            "rows": list(rng.values(name=F("action")).annotate(count=Count("id")).order_by("-count")[:30])},
                           {"title": "حسب المنفّذ", "columns": cols(("name", "المنفّذ"), ("count", "العدد")),
                            "rows": list(rng.values(name=F("actor_label")).annotate(count=Count("id")).order_by("-count")[:30])}]}


BUILDERS = {"users": report_users, "teachers": report_teachers, "students": report_students, "environments": report_environments,
            "tickets": report_tickets, "agents": report_agents, "finance": report_finance, "ai": report_ai,
            "notifications": report_notifications, "admin_activity": report_admin_activity}


class ReportListView(ControlView):
    perm = "reports.view"

    def get(self, request):
        return Response([{"key": k, "title": t} for k, t in REPORTS.items() if not DOMAIN_PERM.get(k) or can(request, DOMAIN_PERM[k])])


class ReportView(ControlView):
    perm = "reports.view"

    def get(self, request, name):
        if name not in BUILDERS:
            return Response({"detail": "تقرير غير موجود.", "code": "not_found"}, status=404)
        need = DOMAIN_PERM.get(name)
        if need and not can(request, need):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("هذا التقرير يتطلب صلاحية إضافية.")
        start, end, _, label = parse_range(request, "30d")
        data = BUILDERS[name](request, start, end)
        data.setdefault("breakdowns", [])
        data.update(key=name, title=REPORTS[name], range=label, from_=iso(start), to=iso(end))
        data["from"] = data.pop("from_")
        if request.query_params.get("export") == "csv":
            table = data.get("detail") or data
            header = [c["label"] for c in table["columns"]]
            rows = [[r.get(c["key"]) for c in table["columns"]] for r in table["rows"]]
            return csv_response(f"madar-{name}.csv", header, rows)
        if request.query_params.get("export"):
            raise invalid(export="صيغة غير مدعومة. المتاح: csv. للـ PDF استخدم زر الطباعة في الصفحة.")
        return Response(data)
