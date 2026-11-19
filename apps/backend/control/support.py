"""Support Center endpoints: the team's ticket desk, categories, analytics, and the customers' own ticket API
(teachers and students). Internal notes are only ever serialised for the team."""
from datetime import timedelta

from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from accounts.models import User
from environments.models import Environment

from . import audit, support_services as svc
from .access import HasControlPerm, can, effective_permissions
from .common import ControlView, as_id, date_param, clean_search, csv_response, invalid, iso, ordering, paginate, parse_range, series
from .models import Ticket, TicketAttachment, TicketCategory, TicketEvent, TicketMessage
from .settings_registry import get_setting

DUR = ExpressionWrapper(F("first_response_at") - F("created_at"), output_field=DurationField())
RES = ExpressionWrapper(F("resolved_at") - F("created_at"), output_field=DurationField())


def hours(delta):
    return round(delta.total_seconds() / 3600, 2) if delta is not None else None


class BoundedBody:
    """Mixin for views that take multipart uploads: refuse an oversized declared body BEFORE DRF parses it."""

    def initial(self, request, *args, **kwargs):
        if request.method in ("POST", "PUT", "PATCH"):
            svc.refuse_oversized_request(request)
        super().initial(request, *args, **kwargs)


# ------------------------------------------------------------------ serialisation
def response_status(t):
    if t.status in (Ticket.Status.RESOLVED, Ticket.Status.CLOSED):
        return "done"
    if t.status == Ticket.Status.WAITING or not t.awaiting_team:
        return "awaiting_customer"
    return "awaiting_team"


def ticket_row(t):
    return {
        "id": t.id, "number": t.number, "subject": t.subject, "kind": t.kind, "status": t.status, "priority": t.priority,
        "category": {"id": t.category_id, "name": t.category.name},
        "requester": {"id": t.requester_id, "name": t.requester_name, "kind": t.requester_kind},
        "assignee": {"id": t.assignee_id, "name": t.assignee.name} if t.assignee_id else None,
        "response_status": response_status(t), "overdue": svc.is_overdue(t), "due_at": iso(t.due_at),
        "created_at": iso(t.created_at), "updated_at": iso(t.last_activity_at), "reopen_count": t.reopen_count,
    }


def attachment_json(a):
    return {"id": a.id, "name": a.original_name, "content_type": a.content_type, "size": a.size}


def message_json(m):
    return {"id": m.id, "kind": m.kind, "author": m.author_name or (m.author.name if m.author_id else ""),
            "author_id": m.author_id, "body": m.body, "created_at": iso(m.created_at),
            "attachments": [attachment_json(a) for a in m.attachments.all()]}


EVENT_TEXT = {
    "created": "أُنشئت التذكرة", "status": "تغيّرت الحالة", "priority": "تغيّرت الأولوية", "assigned": "تغيّر الإسناد",
    "category": "تغيّر التصنيف", "reply": "ردّ الفريق", "note": "أُضيفت ملاحظة داخلية", "customer_reply": "ردّ العميل",
    "reopened": "أُعيد فتح التذكرة", "rated": "قيّم العميل الخدمة",
}


def event_json(e):
    return {"id": e.id, "kind": e.kind, "text": EVENT_TEXT.get(e.kind, e.kind), "actor": e.actor_name,
            "from": e.from_value, "to": e.to_value, "at": iso(e.created_at)}


def ticket_detail(t, request):
    perms = effective_permissions(request.user)
    d = ticket_row(t)
    d.update({
        "description": t.description, "source": t.source, "first_response_at": iso(t.first_response_at),
        "resolved_at": iso(t.resolved_at), "closed_at": iso(t.closed_at),
        "rating": t.rating, "rating_comment": t.rating_comment,
        "messages": [message_json(m) for m in t.messages.prefetch_related("attachments").select_related("author")],
        "history": [event_json(e) for e in t.events.all()],
        "customer": customer_info(t),
        "allowed_statuses": [s for s in svc.TRANSITIONS[t.status]
                             if ((s in svc.NEEDS_RESOLVE or t.status in svc.REOPEN_FROM) and "tickets.resolve" in perms)
                             or ("tickets.reply" in perms and s not in svc.NEEDS_RESOLVE and t.status not in svc.REOPEN_FROM)],
    })
    return d


def customer_info(t):
    u = t.requester
    info = {"name": t.requester_name, "kind": t.requester_kind, "email": t.requester_email, "phone": t.requester_phone,
            "environment": {"id": t.environment_id, "name": t.environment.name} if t.environment_id else None,
            "user_id": t.requester_id}
    if u:
        from .users import account_status

        info.update(account_status=account_status(u), joined=iso(u.date_joined),
                    open_tickets=Ticket.objects.filter(requester=u, status__in=Ticket.ACTIVE).count(),
                    total_tickets=Ticket.objects.filter(requester=u).count())
    return info


# ------------------------------------------------------------------ team: list
def filtered_tickets(request):
    q = request.query_params
    qs = Ticket.objects.select_related("category", "assignee", "requester")
    for param, field in (("status", "status"), ("priority", "priority"), ("kind", "kind"), ("category", "category_id"),
                         ("requester_kind", "requester_kind")):
        if q.get(param):
            qs = qs.filter(**{field: q[param]})
    a = q.get("assignee")
    if a == "me":
        qs = qs.filter(assignee=request.user)
    elif a == "none":
        qs = qs.filter(assignee__isnull=True)
    elif a:
        if (aid := as_id(a)) is None:
            raise invalid(assignee="قيمة غير صالحة.")
        qs = qs.filter(assignee_id=aid)
    if q.get("unassigned") == "1":
        qs = qs.filter(assignee__isnull=True, status__in=Ticket.ACTIVE)
    if q.get("mine") == "1":
        qs = qs.filter(assignee=request.user)
    if q.get("active") == "1":
        qs = qs.filter(status__in=Ticket.ACTIVE)
    if q.get("overdue") == "1":
        qs = qs.filter(status__in=Ticket.WORKING, due_at__lt=svc.now())
    if q.get("response") == "awaiting_team":
        qs = qs.filter(status__in=Ticket.ACTIVE, awaiting_team=True).exclude(status=Ticket.Status.WAITING)
    if d := date_param(request, "created_from"):
        qs = qs.filter(created_at__date__gte=d)
    if d := date_param(request, "created_to"):
        qs = qs.filter(created_at__date__lte=d)
    if s := clean_search(request):
        digits = s.upper().replace("MDR-", "").lstrip("0")
        cond = (Q(subject__icontains=s) | Q(requester_name__icontains=s) | Q(requester_phone__icontains=s)
                | Q(requester_email__icontains=s))
        if (tid := as_id(digits)) is not None:
            cond |= Q(pk=tid)
        qs = qs.filter(cond)
    return qs.order_by(*ordering(request, {"created_at": "created_at", "updated_at": "last_activity_at",
                                           "priority": "priority", "status": "status", "id": "id"}, "-updated_at"))


class TicketCreateSerializer(serializers.Serializer):
    subject = serializers.CharField(max_length=200)
    description = serializers.CharField(max_length=5000)
    category = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=Ticket.Kind.choices, default="ticket")
    priority = serializers.ChoiceField(choices=Ticket.Priority.choices, default="medium")
    # who the ticket is for
    requester_user = serializers.IntegerField(required=False)
    requester_kind = serializers.ChoiceField(choices=Ticket.RequesterKind.choices, required=False)
    requester_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    requester_phone = serializers.CharField(max_length=20, required=False, allow_blank=True)
    requester_email = serializers.CharField(max_length=254, required=False, allow_blank=True)

    def validate_subject(self, v):
        v = v.strip()
        if len(v) < 3:
            raise serializers.ValidationError("العنوان قصير جدًا.")
        return v

    def validate_description(self, v):
        v = v.strip()
        if len(v) < 5:
            raise serializers.ValidationError("اكتب وصفًا أوضح للمشكلة.")
        return v


class TicketListCreateView(BoundedBody, ControlView):
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def get_permissions(self):
        return [HasControlPerm.require("tickets.create" if self.request.method == "POST" else "tickets.view")()]

    def get(self, request):
        if request.query_params.get("export") == "csv":
            if not can(request, "reports.view"):
                from rest_framework.exceptions import PermissionDenied

                raise PermissionDenied("تصدير التذاكر يتطلب صلاحية التقارير.")
            return csv_response("tickets.csv", ["الرقم", "العنوان", "النوع", "الحالة", "الأولوية", "التصنيف", "العميل",
                                                "المسند إليه", "تاريخ الإنشاء"],
                                [[t.number, t.subject, t.kind, t.status, t.priority, t.category.name, t.requester_name,
                                  t.assignee.name if t.assignee else "", iso(t.created_at)]
                                 for t in filtered_tickets(request)[:5000]])
        return Response(paginate(request, filtered_tickets(request), ticket_row))

    def post(self, request):
        ser = TicketCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        category = svc.active_category(d["category"])
        if not category:
            raise invalid(category="تصنيف غير صالح.")
        user = None
        name, kind, phone, email, env = d.get("requester_name", ""), d.get("requester_kind", "other"), \
            d.get("requester_phone", ""), d.get("requester_email", ""), None
        if d.get("requester_user"):
            user = User.objects.filter(pk=d["requester_user"], role__in=("teacher", "student")).first()
            if not user:
                raise invalid(requester_user="المستخدم غير موجود.")
            name, kind, phone, email = user.name, user.role, user.phone or "", user.email or ""
            env = _default_environment(user)
        elif not name.strip():
            raise invalid(requester_name="اسم العميل مطلوب عند عدم اختيار حساب.")
        t = svc.create_ticket(
            subject=d["subject"], description=d["description"], category=category, kind=d["kind"], requester=user,
            requester_kind=kind, name=name.strip(), email=email, phone=phone, environment=env, source="staff",
            created_by=request.user, priority=d["priority"], files=request.FILES.getlist("files"))
        audit.record(request, "ticket.create", "ticket", t.id, t.number, after={"subject": t.subject, "on_behalf_of": name})
        return Response(ticket_detail(t, request), status=201)


def _default_environment(user):
    if user.role == "teacher":
        return Environment.objects.filter(owner=user).first()
    ids = list(user.enrollments.values_list("environment_id", flat=True)[:2])
    return Environment.objects.filter(pk=ids[0]).first() if len(ids) == 1 else None


# ------------------------------------------------------------------ team: one ticket
def _ticket(pk):
    return get_object_or_404(Ticket.objects.select_related("category", "assignee", "requester", "environment"), pk=pk)


class TicketDetailView(ControlView):
    perm = "tickets.view"

    def get(self, request, pk):
        t = _ticket(pk)
        audit.record_view(request, "ticket", t.id, t.number)
        return Response(ticket_detail(t, request))


class MessageSerializer(serializers.Serializer):
    body = serializers.CharField(max_length=5000)
    kind = serializers.ChoiceField(choices=["reply", "note", "request_info"], default="reply")

    def validate_body(self, v):
        v = v.strip()
        if not v:
            raise serializers.ValidationError("اكتب نص الرسالة.")
        return v


class TicketMessageView(BoundedBody, ControlView):
    perm = "tickets.reply"
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def post(self, request, pk):
        t = _ticket(pk)
        ser = MessageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d, files = ser.validated_data, request.FILES.getlist("files")
        if d["kind"] == "note":
            svc.internal_note(t, request.user, d["body"], files)
            audit.record(request, "ticket.note", "ticket", t.id, t.number)
        else:
            svc.staff_reply(t, request.user, d["body"], request_info=d["kind"] == "request_info", files=files)
            audit.record(request, "ticket.reply", "ticket", t.id, t.number,
                         after={"request_info": d["kind"] == "request_info"})
        t.refresh_from_db()
        return Response(ticket_detail(_ticket(pk), request), status=201)


class _StatusSerializer(serializers.Serializer):
    status = serializers.CharField()
    note = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class TicketStatusView(ControlView):
    perm = ("tickets.reply", "tickets.resolve")

    def post(self, request, pk):
        t = _ticket(pk)
        ser = _StatusSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        svc.change_status(t, request.user, ser.validated_data["status"], can(request, "tickets.resolve"),
                          can(request, "tickets.reply"), request, ser.validated_data["note"].strip())
        return Response(ticket_detail(_ticket(pk), request))


class _PrioritySerializer(serializers.Serializer):
    priority = serializers.CharField()


class TicketPriorityView(ControlView):
    perm = "tickets.priority"

    def post(self, request, pk):
        t = _ticket(pk)
        ser = _PrioritySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        svc.change_priority(t, request.user, ser.validated_data["priority"], request)
        return Response(ticket_detail(_ticket(pk), request))


class _CategorySerializer(serializers.Serializer):
    category = serializers.IntegerField()


class TicketCategoryChangeView(ControlView):
    perm = "tickets.reply"

    def post(self, request, pk):
        t = _ticket(pk)
        ser = _CategorySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        cat = TicketCategory.objects.filter(pk=ser.validated_data["category"]).first()
        if not cat:
            raise invalid(category="تصنيف غير صالح.")
        svc.change_category(t, request.user, cat, request)
        return Response(ticket_detail(_ticket(pk), request))


class _AssignSerializer(serializers.Serializer):
    assignee = serializers.IntegerField(allow_null=True)


def resolve_assignee(request, assignee_id):
    """-> team User or None. A person can claim an unassigned ticket for themselves with `tickets.reply`;
    everything else (giving a ticket to someone else, taking it away) needs `tickets.assign`."""
    from rest_framework.exceptions import PermissionDenied

    if assignee_id is None:
        if not can(request, "tickets.assign"):
            raise PermissionDenied("إلغاء الإسناد يتطلب صلاحية «إسناد التذاكر».")
        return None
    agent = User.objects.filter(pk=assignee_id, role="team", is_active=True).first()
    if not agent or "tickets.reply" not in effective_permissions(agent):
        raise invalid(assignee="هذا العضو لا يستطيع العمل على التذاكر.")
    if agent.pk != request.user.pk and not can(request, "tickets.assign"):
        raise PermissionDenied("إسناد التذاكر لغيرك يتطلب صلاحية «إسناد التذاكر».")
    return agent


class TicketAssignView(ControlView):
    perm = ("tickets.assign", "tickets.reply")

    def post(self, request, pk):
        t = _ticket(pk)
        ser = _AssignSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        agent = resolve_assignee(request, ser.validated_data["assignee"])
        if (agent is None or (t.assignee_id and t.assignee_id != agent.pk)) and not can(request, "tickets.assign"):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("إعادة إسناد تذكرة مسندة لغيرك تتطلب صلاحية «إسناد التذاكر».")
        svc.assign(t, request.user, agent, request)
        return Response(ticket_detail(_ticket(pk), request))


class _BulkSerializer(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(), min_length=1, max_length=100)
    action = serializers.ChoiceField(choices=["assign", "status", "priority"])
    value = serializers.JSONField(allow_null=True)


class TicketBulkView(ControlView):
    perm = ("tickets.assign", "tickets.priority", "tickets.reply", "tickets.resolve")

    def post(self, request):
        ser = _BulkSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        from rest_framework.exceptions import APIException, PermissionDenied

        agent = resolve_assignee(request, d["value"]) if d["action"] == "assign" else None
        if d["action"] == "priority" and not can(request, "tickets.priority"):
            raise PermissionDenied("تغيير الأولوية يتطلب صلاحية «تغيير أولوية التذكرة».")
        results = []
        for t in Ticket.objects.filter(pk__in=d["ids"]).select_related("category", "assignee", "requester"):
            try:
                if d["action"] == "assign":
                    if t.assignee_id and t.assignee_id != getattr(agent, "pk", None) and not can(request, "tickets.assign"):
                        raise PermissionDenied("لا يمكنك إعادة الإسناد.")
                    svc.assign(t, request.user, agent, request)
                elif d["action"] == "status":
                    svc.change_status(t, request.user, d["value"], can(request, "tickets.resolve"),
                                      can(request, "tickets.reply"), request)
                else:
                    svc.change_priority(t, request.user, d["value"], request)
                results.append({"id": t.id, "ok": True})
            except (APIException, ValueError) as exc:
                detail = exc.detail if hasattr(exc, "detail") else str(exc)
                results.append({"id": t.id, "ok": False, "error": _flat(detail)})
        found = {r["id"] for r in results}
        results += [{"id": i, "ok": False, "error": "غير موجودة"} for i in d["ids"] if i not in found]
        audit.record(request, "ticket.bulk", "ticket", "", f"{len(d['ids'])} تذكرة", after={
            "action": d["action"], "value": d["value"], "ok": sum(1 for r in results if r["ok"])})
        return Response({"results": results, "ok": sum(1 for r in results if r["ok"]), "failed": sum(1 for r in results if not r["ok"])})


def _flat(detail):
    if isinstance(detail, dict):
        detail = next(iter(detail.values()), "")
    if isinstance(detail, (list, tuple)):
        detail = detail[0] if detail else ""
    return str(detail)


# ------------------------------------------------------------------ attachments
def serve_attachment(att):
    try:
        resp = FileResponse(att.file.open("rb"), as_attachment=True, filename=att.original_name,
                            content_type=att.content_type)
    except (FileNotFoundError, ValueError):
        raise Http404
    resp["X-Content-Type-Options"] = "nosniff"
    resp["Content-Security-Policy"] = "default-src 'none'; sandbox"
    resp["Cache-Control"] = "private, no-store"
    return resp


class TeamAttachmentView(ControlView):
    perm = "tickets.view"

    def get(self, request, pk):
        return serve_attachment(get_object_or_404(TicketAttachment, pk=pk))


# ------------------------------------------------------------------ categories
class _CategoryWrite(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    description = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    order = serializers.IntegerField(required=False, min_value=0, max_value=1000)
    is_active = serializers.BooleanField(required=False)


def category_json(c):
    return {"id": c.id, "name": c.name, "description": c.description, "order": c.order, "is_active": c.is_active,
            "tickets": c.tickets.count()}


class CategoryListCreateView(ControlView):
    def get_permissions(self):
        return [HasControlPerm.require("tickets.categories" if self.request.method == "POST" else "tickets.view")()]

    def get(self, request):
        return Response([category_json(c) for c in TicketCategory.objects.all()])

    def post(self, request):
        ser = _CategoryWrite(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if TicketCategory.objects.filter(name__iexact=d["name"].strip()).exists():
            raise invalid(name="يوجد تصنيف بهذا الاسم.")
        c = TicketCategory.objects.create(name=d["name"].strip(), description=d["description"], order=d.get("order", 100))
        audit.record(request, "ticket_category.create", "ticket_category", c.id, c.name)
        return Response(category_json(c), status=201)


class CategoryDetailView(ControlView):
    perm = "tickets.categories"

    def patch(self, request, pk):
        c = get_object_or_404(TicketCategory, pk=pk)
        ser = _CategoryWrite(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if "name" in d and TicketCategory.objects.filter(name__iexact=d["name"].strip()).exclude(pk=c.pk).exists():
            raise invalid(name="يوجد تصنيف بهذا الاسم.")
        before = {k: getattr(c, k) for k in d}
        for k, v in d.items():
            setattr(c, k, v.strip() if isinstance(v, str) else v)
        c.save()
        audit.record(request, "ticket_category.update", "ticket_category", c.id, c.name, *audit.diff(before, d))
        return Response(category_json(c))

    def delete(self, request, pk):
        c = get_object_or_404(TicketCategory, pk=pk)
        if c.tickets.exists():
            raise invalid(detail="لا يمكن حذف تصنيف يحتوي تذاكر. عطّله بدلًا من ذلك.")
        audit.record(request, "ticket_category.delete", "ticket_category", c.id, c.name)
        c.delete()
        return Response(status=204)


# ------------------------------------------------------------------ overview & analytics
class SupportOverviewView(ControlView):
    perm = "tickets.view"

    def get(self, request):
        start, end, _, label = parse_range(request, "30d")
        qs = Ticket.objects.all()
        active = qs.filter(status__in=Ticket.ACTIVE)
        in_range = qs.filter(created_at__gte=start, created_at__lt=end)
        resolved_range = qs.filter(resolved_at__gte=start, resolved_at__lt=end)
        return Response({
            "range": label,
            "total": qs.count(), "open": qs.filter(status="open").count(), "in_progress": qs.filter(status="in_progress").count(),
            "waiting_for_user": qs.filter(status="waiting_for_user").count(), "resolved": qs.filter(status="resolved").count(),
            "closed": qs.filter(status="closed").count(),
            "unassigned": active.filter(assignee__isnull=True).count(),
            "high_priority": active.filter(priority__in=("high", "critical")).count(),
            "overdue": qs.filter(status__in=Ticket.WORKING, due_at__lt=svc.now()).count(),
            "avg_first_response_hours": hours(in_range.filter(first_response_at__isnull=False).aggregate(v=Avg(DUR))["v"]),
            "avg_resolution_hours": hours(resolved_range.aggregate(v=Avg(RES))["v"]),
        })


def agent_workload():
    limit = int(get_setting("tickets.agent_overload"))
    agents = [u for u in User.objects.filter(role="team", is_active=True).select_related("team_profile__role")
              if "tickets.reply" in effective_permissions(u)]
    active = dict(Ticket.objects.filter(status__in=Ticket.ACTIVE, assignee__isnull=False).values_list("assignee_id")
                  .annotate(n=Count("id")))
    resolved = dict(Ticket.objects.filter(status__in=("resolved", "closed"), assignee__isnull=False)
                    .values_list("assignee_id").annotate(n=Count("id")))
    return [{"id": a.id, "name": a.name, "role": a.team_profile.role.name if hasattr(a, "team_profile") else "",
             "active": active.get(a.id, 0), "resolved": resolved.get(a.id, 0), "overloaded": active.get(a.id, 0) >= limit}
            for a in agents]


class AgentListView(ControlView):
    """Who can be given a ticket, with their current load — the picker in the assign dialog and the workload board."""

    perm = ("tickets.view",)

    def get(self, request):
        return Response(sorted(agent_workload(), key=lambda a: a["active"]))


class SupportAnalyticsView(ControlView):
    perm = ("support.analytics", "tickets.view")

    def get(self, request):
        start, end, prev_start, label = parse_range(request, "30d")
        created = Ticket.objects.filter(created_at__gte=start, created_at__lt=end)
        done = Ticket.objects.filter(resolved_at__gte=start, resolved_at__lt=end)
        n_created = created.count()
        n_done = done.count()
        reopened = TicketEvent.objects.filter(kind="reopened", created_at__gte=start, created_at__lt=end).values("ticket").distinct().count()
        rated = Ticket.objects.filter(rated_at__gte=start, rated_at__lt=end)
        per_agent = list(Ticket.objects.filter(assignee__isnull=False, created_at__gte=start, created_at__lt=end)
                         .values("assignee__id", "assignee__name")
                         .annotate(assigned=Count("id"), resolved=Count("id", filter=Q(status__in=("resolved", "closed"))),
                                   avg_rating=Avg("rating"), avg_response=Avg(DUR)).order_by("-assigned"))
        return Response({
            "range": label,
            "volume": {"created": series(Ticket.objects.all(), "created_at", start, end),
                       "resolved": series(Ticket.objects.all(), "resolved_at", start, end)},
            "by_category": list(created.values(name=F("category__name")).annotate(count=Count("id")).order_by("-count")),
            "by_priority": list(created.values("priority").annotate(count=Count("id")).order_by("-count")),
            "by_status": list(created.values("status").annotate(count=Count("id")).order_by("-count")),
            "created": n_created, "resolved": n_done,
            "resolution_rate": round(n_done * 100 / n_created, 1) if n_created else None,
            "avg_response_hours": hours(created.filter(first_response_at__isnull=False).aggregate(v=Avg(DUR))["v"]),
            "avg_resolution_hours": hours(done.aggregate(v=Avg(RES))["v"]),
            "reopened": reopened, "reopen_rate": round(reopened * 100 / n_done, 1) if n_done else None,
            "common_complaints": list(created.filter(kind="complaint").values(name=F("category__name"))
                                      .annotate(count=Count("id")).order_by("-count")[:8]),
            "agents": [{"id": a["assignee__id"], "name": a["assignee__name"], "assigned": a["assigned"],
                        "resolved": a["resolved"], "avg_rating": round(a["avg_rating"], 2) if a["avg_rating"] else None,
                        "avg_response_hours": hours(a["avg_response"])} for a in per_agent],
            "workload": agent_workload(),
            "satisfaction": {
                "count": rated.count(),
                "average": round(rated.aggregate(v=Avg("rating"))["v"] or 0, 2) or None,
                "distribution": {str(i): rated.filter(rating=i).count() for i in range(1, 6)},
                "low_rating_feedback": [{"ticket": t.number, "rating": t.rating, "comment": t.rating_comment,
                                        "category": t.category.name}
                                       for t in rated.filter(rating__lte=2).exclude(rating_comment="").select_related("category")[:10]],
            },
        })


# ------------------------------------------------------------------ customers (teachers & students)
class CustomerView(BoundedBody, APIView):
    """Teachers and students only. A guardian session (ParentPrincipal) and team accounts are refused: a guardian
    has no account to attach a ticket to, and the team uses the Control Center."""

    permission_classes = [IsAuthenticated]
    parser_classes = [JSONParser, MultiPartParser, FormParser]

    def initial(self, request, *args, **kwargs):
        super().initial(request, *args, **kwargs)
        if getattr(request.user, "role", None) not in ("teacher", "student"):
            from rest_framework.exceptions import PermissionDenied

            raise PermissionDenied("الدعم متاح للمعلّمين والطلاب.")


def customer_ticket(t):
    return {
        "id": t.id, "number": t.number, "subject": t.subject, "kind": t.kind, "status": t.status,
        "category": t.category.name, "created_at": iso(t.created_at), "updated_at": iso(t.last_activity_at),
        "response_status": response_status(t),
    }


def customer_detail(t):
    d = customer_ticket(t)
    d.update({
        "description": t.description, "rating": t.rating, "rating_comment": t.rating_comment,
        # Internal notes are filtered out at the QUERY, not hidden in the UI.
        "messages": [message_json(m) for m in t.messages.exclude(kind="internal").prefetch_related("attachments")],
        "can_reply": not (t.status == "closed" and (not t.closed_at or svc.now() - t.closed_at > timedelta(days=int(get_setting("tickets.reopen_days"))))),
        "can_rate": t.status in ("resolved", "closed") and t.rating is None,
    })
    return d


class CustomerCategoriesView(CustomerView):
    def get(self, request):
        return Response([{"id": c.id, "name": c.name} for c in TicketCategory.objects.filter(is_active=True)])


class CustomerTicketsView(CustomerView):
    def get_throttles(self):
        if self.request.method == "POST":
            self.throttle_scope = "support-write"
            return [ScopedRateThrottle()]
        return []

    def get(self, request):
        qs = Ticket.objects.filter(requester=request.user).select_related("category")
        return Response([customer_ticket(t) for t in qs[:100]])

    def post(self, request):
        class S(TicketCreateSerializer):
            environment = serializers.IntegerField(required=False)

        ser = S(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        category = svc.active_category(d["category"])
        if not category:
            raise invalid(category="تصنيف غير صالح.")
        u = request.user
        env = None
        if u.role == "teacher":
            env = Environment.objects.filter(owner=u).first()
        elif d.get("environment"):  # only an environment this student really belongs to
            env = Environment.objects.filter(pk=d["environment"], memberships__user=u).first()
            if env is None:
                raise invalid(environment="لا تنتمي لهذه البيئة.")
        else:
            env = _default_environment(u)
        t = svc.create_ticket(
            subject=d["subject"], description=d["description"], category=category,
            kind=d["kind"] if d["kind"] in ("ticket", "complaint") else "ticket", requester=u, requester_kind=u.role,
            name=u.name, email=u.email or "", phone=u.phone or "", environment=env, source="customer",
            priority="medium", files=request.FILES.getlist("files"))
        return Response(customer_detail(t), status=201)


def _own(request, pk):
    return get_object_or_404(Ticket.objects.select_related("category"), pk=pk, requester=request.user)


class CustomerTicketDetailView(CustomerView):
    def get(self, request, pk):
        return Response(customer_detail(_own(request, pk)))


class _CustomerMessage(serializers.Serializer):
    body = serializers.CharField(max_length=5000)

    def validate_body(self, v):
        v = v.strip()
        if not v:
            raise serializers.ValidationError("اكتب نص الرسالة.")
        return v


class CustomerMessageView(CustomerView):
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "support-write"

    def post(self, request, pk):
        t = _own(request, pk)
        ser = _CustomerMessage(data=request.data)
        ser.is_valid(raise_exception=True)
        svc.customer_reply(t, request.user, ser.validated_data["body"], request.FILES.getlist("files"))
        return Response(customer_detail(_own(request, pk)), status=201)


class _Rating(serializers.Serializer):
    rating = serializers.IntegerField(min_value=1, max_value=5)
    comment = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class CustomerRateView(CustomerView):
    def post(self, request, pk):
        t = _own(request, pk)
        ser = _Rating(data=request.data)
        ser.is_valid(raise_exception=True)
        svc.rate(t, request.user, ser.validated_data["rating"], ser.validated_data["comment"].strip())
        return Response(customer_detail(_own(request, pk)))


class CustomerAttachmentView(CustomerView):
    def get(self, request, pk):
        att = get_object_or_404(TicketAttachment.objects.exclude(message__kind="internal"), pk=pk,
                                message__ticket__requester=request.user)
        return serve_attachment(att)
