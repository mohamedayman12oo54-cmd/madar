"""Business operations: financial monitoring (Madar's own subscription billing), AI operation monitoring, and
notification management. All READ-ONLY views over the existing billing / ai / notifications tables, except the
audited platform-notice sending and template management.

Money safety: nothing here can change a payment's or a subscription's state. Success is whatever the existing,
signature-verified provider flow (billing/) wrote; this module only reads it. Card tokens, agreement ids and raw
provider payloads are never selected."""
from datetime import timedelta

from django.conf import settings
from django.db.models import Avg, Count, DurationField, ExpressionWrapper, F, Q, Sum
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response

from accounts.models import User
from ai.models import AIOperation
from billing.models import PaymentAttempt, Plan, ProviderEvent, Subscription
from environments.models import Environment
from notifications import webpush
from notifications.models import Notification, PushSubscription

from . import audit, platform_notices as pn
from .access import HasControlPerm
from .common import ControlView, id_param, date_param, clean_search, csv_response, invalid, iso, ordering, paginate, parse_range, series
from .models import NotificationTemplate, PlatformNotice, Ticket
from .settings_registry import get_setting
from .support_services import now

PA = PaymentAttempt.Status


# ================================================================== finance
def attempt_row(a):
    return {
        "id": a.id, "transaction_id": a.merchant_order_id, "environment": {"id": a.environment_id, "name": a.environment.name},
        "owner": a.environment.owner.name, "plan": a.plan.name if a.plan else None,
        "amount": a.amount_minor_units / 100, "currency": a.currency, "provider": "Kashier",
        "kind": "renewal" if a.billing_period_id else "checkout", "status": a.status, "status_label": a.get_status_display(),
        "reference": a.provider_order_id or "", "provider_transaction_id": a.provider_transaction_id or "",
        "created_at": iso(a.created_at), "updated_at": iso(a.updated_at),
    }


def filtered_attempts(request):
    q = request.query_params
    qs = PaymentAttempt.objects.select_related("environment__owner", "plan")
    if st := q.get("status"):
        qs = qs.filter(status__in=PaymentAttempt.NON_TERMINAL_STATUSES) if st == "pending" else qs.filter(status=st)
    if (_environment := id_param(request, "environment")) is not None:
        qs = qs.filter(environment_id=_environment)
    if (_from := date_param(request, "from")):
        qs = qs.filter(created_at__date__gte=_from)
    if (_to := date_param(request, "to")):
        qs = qs.filter(created_at__date__lte=_to)
    if s := clean_search(request):
        qs = qs.filter(Q(merchant_order_id__icontains=s) | Q(provider_order_id__icontains=s)
                       | Q(provider_transaction_id__icontains=s) | Q(environment__name__icontains=s)
                       | Q(environment__owner__name__icontains=s))
    return qs.order_by(*ordering(request, {"created_at": "created_at", "amount": "amount_minor_units", "status": "status"}, "-created_at"))


class FinanceOverviewView(ControlView):
    perm = "finance.view"

    def get(self, request):
        start, end, _, label = parse_range(request, "30d")
        att = PaymentAttempt.objects.filter(created_at__gte=start, created_at__lt=end)
        ok = PaymentAttempt.objects.filter(status=PA.SUCCEEDED)
        by_status = dict(att.values_list("status").annotate(n=Count("id")))
        subs = dict(Subscription.objects.values_list("state").annotate(n=Count("id")))
        return Response({
            "range": label, "total": att.count(), "succeeded": by_status.get("succeeded", 0), "failed": by_status.get("failed", 0),
            "pending": PaymentAttempt.objects.filter(status__in=PaymentAttempt.NON_TERMINAL_STATUSES).count(),
            "unknown": PaymentAttempt.objects.filter(status=PA.UNKNOWN).count(),
            "subscriptions": {"active": subs.get("active", 0), "trial": subs.get("trial", 0), "past_due": subs.get("past_due", 0),
                              "canceled": subs.get("canceled", 0), "expired": subs.get("expired", 0)},
            "revenue": {"period": [{"currency": c, "amount": (s or 0) / 100} for c, s in
                                   att.filter(status=PA.SUCCEEDED).values_list("currency").annotate(s=Sum("amount_minor_units"))],
                        "all_time": [{"currency": c, "amount": (s or 0) / 100} for c, s in
                                     ok.values_list("currency").annotate(s=Sum("amount_minor_units"))]},
            "charts": {
                "succeeded": series(ok, "created_at", start, end),
                "failed": series(PaymentAttempt.objects.filter(status=PA.FAILED), "created_at", start, end),
                "revenue": _revenue_series(start, end),
            },
        })


def _revenue_series(start, end):
    from django.db.models.functions import TruncDate

    rows = dict(PaymentAttempt.objects.filter(status=PA.SUCCEEDED, created_at__gte=start, created_at__lt=end)
                .annotate(d=TruncDate("created_at")).values_list("d").annotate(s=Sum("amount_minor_units")))
    from .common import day_list

    return [{"date": d.isoformat(), "value": (rows.get(d) or 0) / 100} for d in day_list(start, end)]


class TransactionListView(ControlView):
    perm = "finance.view"

    def get(self, request):
        if request.query_params.get("export") == "csv":
            return csv_response("transactions.csv", ["المعاملة", "البيئة", "المعلّم", "المبلغ", "العملة", "الحالة", "المرجع", "التاريخ"],
                                [[a.merchant_order_id, a.environment.name, a.environment.owner.name, a.amount_minor_units / 100,
                                  a.currency, a.status, a.provider_order_id or "", iso(a.created_at)]
                                 for a in filtered_attempts(request)[:5000]])
        return Response(paginate(request, filtered_attempts(request), attempt_row))


def sub_row(s):
    renews = s.state in ("active",) and not s.cancel_at_period_end and s.active_agreement_id is not None
    return {
        "id": s.id, "environment": {"id": s.environment_id, "name": s.environment.name}, "owner": s.environment.owner.name,
        "plan": s.plan.name if s.plan else None, "plan_key": s.plan.key if s.plan else None, "state": s.state,
        "state_label": s.get_state_display(), "trial_ends_at": iso(s.trial_ends_at),
        "period_start": iso(s.current_period_start), "period_end": iso(s.current_period_end),
        "cancel_at_period_end": s.cancel_at_period_end,
        "renewal": "auto" if renews else ("canceled" if s.cancel_at_period_end else "manual"),
    }


class SubscriptionListView(ControlView):
    perm = "finance.view"

    def get(self, request):
        qs = Subscription.objects.select_related("environment__owner", "plan")
        if st := request.query_params.get("state"):
            qs = qs.filter(state=st)
        if s := clean_search(request):
            qs = qs.filter(Q(environment__name__icontains=s) | Q(environment__owner__name__icontains=s))
        qs = qs.order_by(*ordering(request, {"period_end": "current_period_end", "state": "state", "id": "id"}, "-id"))
        return Response(paginate(request, qs, sub_row))


class PlanListView(ControlView):
    perm = "finance.view"

    def get(self, request):
        counts = dict(Subscription.objects.filter(state="active").values_list("plan_id").annotate(n=Count("id")))
        return Response([{"id": p.id, "key": p.key, "name": p.name, "price": p.price_minor_units / 100, "currency": p.currency,
                          "period_days": p.period_days, "max_students": p.max_students, "is_active": p.is_active,
                          "active_subscriptions": counts.get(p.id, 0)} for p in Plan.objects.all()])


class PaymentIssuesView(ControlView):
    perm = "finance.view"

    def get(self, request):
        since = now() - timedelta(days=int(get_setting("payments.attention_days")))
        stuck = now() - timedelta(minutes=30)
        failed = PaymentAttempt.objects.filter(status=PA.FAILED, created_at__gte=since)
        unknown = PaymentAttempt.objects.filter(status=PA.UNKNOWN)
        pending = PaymentAttempt.objects.filter(status__in=(PA.INITIATED, PA.PENDING), updated_at__lt=stuck)
        events = ProviderEvent.objects.filter(Q(processing_status="failed_to_apply") | Q(signature_valid=False),
                                              received_at__gte=since)

        def with_tickets(a):
            r = attempt_row(a)
            r["tickets"] = [{"id": t.id, "number": t.number, "status": t.status}
                            for t in Ticket.objects.filter(environment_id=a.environment_id)[:3]]
            return r

        sel = "environment__owner", "plan"
        return Response({
            "window_days": int(get_setting("payments.attention_days")),
            "failed": [with_tickets(a) for a in failed.select_related(*sel)[:50]],
            "needs_reconciliation": [with_tickets(a) for a in unknown.select_related(*sel)[:50]],
            "pending_too_long": [with_tickets(a) for a in pending.select_related(*sel)[:50]],
            # Verification problems: provider events whose signature did not verify or that could not be applied.
            "verification": [{"id": e.id, "event_type": e.event_type, "transaction_status": e.transaction_status,
                              "signature_valid": e.signature_valid, "processing_status": e.processing_status,
                              "attempts": e.attempts_count, "error": e.last_error,
                              "environment": e.environment.name if e.environment_id else None, "received_at": iso(e.received_at)}
                             for e in events.select_related("environment")[:50]],
        })


# ================================================================== AI
DUR = ExpressionWrapper(F("completed_at") - F("started_at"), output_field=DurationField())
SAFE_META = ("prompt_version", "max_attempts", "attempts", "provider_attempts", "validation", "failure_category",
             "usage", "timings_ms", "exception", "source_chars")


def op_seconds(op):
    if op.started_at and op.completed_at:
        return round((op.completed_at - op.started_at).total_seconds(), 2)
    return None


def op_row(op):
    secs = op_seconds(op)
    return {
        "id": op.id, "kind": op.kind, "kind_label": op.get_kind_display(), "status": op.status, "status_label": op.get_status_display(),
        "user": {"id": op.requested_by_id, "name": op.requested_by.name, "role": op.requested_by.role},
        "environment": {"id": op.environment_id, "name": op.environment.name},
        "created_at": iso(op.created_at), "duration_seconds": secs,
        "slow": bool(secs and secs > int(get_setting("ai.slow_seconds"))),
        "failure_category": (op.metadata or {}).get("failure_category", "") if op.status == "failed" else "",
        "error": op.error,
    }


def filtered_ops(request):
    q = request.query_params
    qs = AIOperation.objects.select_related("requested_by", "environment")
    if q.get("kind"):
        qs = qs.filter(kind=q["kind"])
    if q.get("status"):
        qs = qs.filter(status=q["status"])
    if (_user := id_param(request, "user")) is not None:
        qs = qs.filter(requested_by_id=_user)
    if (_from := date_param(request, "from")):
        qs = qs.filter(created_at__date__gte=_from)
    if (_to := date_param(request, "to")):
        qs = qs.filter(created_at__date__lte=_to)
    if q.get("failure_category"):
        qs = qs.filter(status="failed", metadata__failure_category=q["failure_category"])
    if q.get("slow") == "1":
        qs = qs.filter(completed_at__isnull=False).annotate(_d=DUR).filter(_d__gt=timedelta(seconds=int(get_setting("ai.slow_seconds"))))
    if s := clean_search(request):
        qs = qs.filter(Q(requested_by__name__icontains=s) | Q(error__icontains=s) | Q(environment__name__icontains=s))
    return qs.order_by(*ordering(request, {"created_at": "created_at", "status": "status", "id": "id"}, "-created_at"))


class AIOverviewView(ControlView):
    perm = "ai.view"

    def get(self, request):
        start, end, _, label = parse_range(request, "30d")
        ops = AIOperation.objects.filter(created_at__gte=start, created_at__lt=end)
        by = dict(ops.values_list("status").annotate(n=Count("id")))
        total, done, failed = ops.count(), by.get("completed", 0), by.get("failed", 0)
        finished = done + failed
        cats = {}
        for md in ops.filter(status="failed").values_list("metadata", flat=True):
            c = (md or {}).get("failure_category") or "unknown"
            cats[c] = cats.get(c, 0) + 1
        repeated = (ops.filter(status="failed").values("requested_by_id", "requested_by__name")
                    .annotate(n=Count("id")).filter(n__gte=3).order_by("-n")[:8])
        slow_cut = timedelta(seconds=int(get_setting("ai.slow_seconds")))
        return Response({
            "range": label, "total": total, "completed": done, "failed": failed,
            "pending": by.get("pending", 0) + by.get("processing", 0),
            "success_rate": round(done * 100 / finished, 1) if finished else None,
            "failure_rate": round(failed * 100 / finished, 1) if finished else None,
            "avg_seconds": (lambda d: round(d.total_seconds(), 2) if d else None)(
                ops.filter(completed_at__isnull=False, started_at__isnull=False).aggregate(v=Avg(DUR))["v"]),
            "slow_count": ops.filter(completed_at__isnull=False, started_at__isnull=False).annotate(_d=DUR).filter(_d__gt=slow_cut).count(),
            "by_kind": [{"kind": k, "label": dict(AIOperation.Kind.choices).get(k, k), "count": n}
                        for k, n in ops.values_list("kind").annotate(n=Count("id"))],
            "failure_categories": [{"category": c, "count": n} for c, n in sorted(cats.items(), key=lambda x: -x[1])],
            "repeated_failures": [{"user_id": r["requested_by_id"], "name": r["requested_by__name"], "count": r["n"]} for r in repeated],
            "charts": {"success": series(AIOperation.objects.filter(status="completed"), "created_at", start, end),
                       "failed": series(AIOperation.objects.filter(status="failed"), "created_at", start, end)},
            "provider": settings.AI_PROVIDER,
        })


class AIListView(ControlView):
    perm = "ai.view"

    def get(self, request):
        return Response(paginate(request, filtered_ops(request), op_row))


class AIDetailView(ControlView):
    perm = "ai.view"

    def get(self, request, pk):
        op = get_object_or_404(AIOperation.objects.select_related("requested_by", "environment"), pk=pk)
        md = op.metadata or {}
        d = op_row(op)
        d.update({
            "timeline": [{"key": "created", "at": iso(op.created_at)}, {"key": "started", "at": iso(op.started_at)},
                         {"key": "completed" if op.status == "completed" else "ended", "at": iso(op.completed_at)}],
            "timings_ms": {k: v for k, v in (md.get("timings_ms") or {}).items() if k in ("content_check", "generation", "total")},
            # Request context WITHOUT its private content: the prompt, the lesson text, the evidence and the
            # model's answer are never returned. Only their existence / size is.
            "context": {"has_student": bool(op.enrollment_id), "has_content": bool(op.content_id), "prompt_chars": len(op.prompt or ""),
                        "result_chars": len(op.result or ""), "month": iso(op.month)},
            "metadata": {k: md[k] for k in SAFE_META if k in md},
            "started_at": iso(op.started_at), "completed_at": iso(op.completed_at),
        })
        audit.record_view(request, "ai_operation", op.id, f"#{op.id}")
        return Response(d)


# ================================================================== notifications
def notif_row(n):
    return {
        "id": n.id, "type": n.type, "type_label": n.get_type_display(), "title": n.title,
        "recipient": {"id": n.recipient_id, "name": n.recipient.name, "role": n.recipient.role},
        "environment": {"id": n.environment_id, "name": n.environment.name},
        # pending = queued, sent = handed to the push provider (inbox row is always there), failed = provider refused.
        # `confirmed_read` is the only proof a person actually saw it.
        "status": n.delivery_status, "status_label": n.get_delivery_status_display(), "error": n.delivery_error,
        "created_at": iso(n.created_at), "sent_at": iso(n.delivered_at), "confirmed_read": bool(n.read_at),
    }


def filtered_notifications(request):
    q = request.query_params
    qs = Notification.objects.select_related("recipient", "environment")
    if q.get("type"):
        qs = qs.filter(type=q["type"])
    if q.get("status"):
        qs = qs.filter(delivery_status=q["status"])
    if (_recipient := id_param(request, "recipient")) is not None:
        qs = qs.filter(recipient_id=_recipient)
    if (_environment := id_param(request, "environment")) is not None:
        qs = qs.filter(environment_id=_environment)
    if (_from := date_param(request, "from")):
        qs = qs.filter(created_at__date__gte=_from)
    if (_to := date_param(request, "to")):
        qs = qs.filter(created_at__date__lte=_to)
    if s := clean_search(request):
        qs = qs.filter(Q(title__icontains=s) | Q(recipient__name__icontains=s) | Q(body__icontains=s))
    return qs.order_by(*ordering(request, {"created_at": "created_at", "status": "delivery_status"}, "-created_at"))


class NotificationOverviewView(ControlView):
    perm = "notifications.view"

    def get(self, request):
        start, end, _, label = parse_range(request, "30d")
        qs = Notification.objects.filter(created_at__gte=start, created_at__lt=end)
        by = dict(qs.values_list("delivery_status").annotate(n=Count("id")))
        sent = by.get("sent", 0)
        return Response({
            "range": label, "total": qs.count(), "sent": sent, "pending": by.get("pending", 0), "failed": by.get("failed", 0),
            "read": qs.filter(read_at__isnull=False).count(),
            "by_type": [{"type": t, "label": dict(Notification.Type.choices).get(t, t), "count": n}
                        for t, n in qs.values_list("type").annotate(n=Count("id")).order_by("-n")],
            "push": {"configured": webpush.enabled(), "subscribed_devices": PushSubscription.objects.count(),
                     "subscribed_users": PushSubscription.objects.values("user").distinct().count()},
            "platform_notices": PlatformNotice.objects.filter(created_at__gte=start, created_at__lt=end).count(),
            "charts": {"sent": series(Notification.objects.filter(delivery_status="sent"), "created_at", start, end),
                       "failed": series(Notification.objects.filter(delivery_status="failed"), "created_at", start, end)},
        })


class NotificationListView(ControlView):
    perm = "notifications.view"

    def get(self, request):
        return Response(paginate(request, filtered_notifications(request), notif_row))


class NotificationDetailView(ControlView):
    perm = "notifications.view"

    def get(self, request, pk):
        n = get_object_or_404(Notification.objects.select_related("recipient", "environment"), pk=pk)
        d = notif_row(n)
        d.update(body=n.body, read_at=iso(n.read_at), target=n.target(),
                 push_devices=PushSubscription.objects.filter(user_id=n.recipient_id).count())
        audit.record_view(request, "notification", n.id, n.title)
        return Response(d)


def notice_json(n):
    c = pn.notice_counts(n)
    return {"id": n.id, "title": n.title, "body": n.body, "url": n.url, "audience": n.audience,
            "audience_label": n.get_audience_display(), "environment": n.environment.name if n.environment_id else None,
            "sent_by": n.sent_by.name if n.sent_by_id else "", "recipients": n.recipient_count, "created_at": iso(n.created_at),
            "queued": c["queued"], "sent": c["sent"], "failed": c["failed"], "no_device": c["no_device"]}


class _NoticeSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=150)
    body = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    url = serializers.CharField(max_length=200, required=False, allow_blank=True, default="/")
    audience = serializers.ChoiceField(choices=PlatformNotice.Audience.choices)
    user_ids = serializers.ListField(child=serializers.IntegerField(), required=False, max_length=200)
    environment = serializers.IntegerField(required=False)

    def validate_title(self, v):
        v = v.strip()
        if len(v) < 2:
            raise serializers.ValidationError("اكتب عنوانًا للإشعار.")
        return v

    def validate_url(self, v):
        v = v.strip() or "/"
        if not pn.valid_url(v):
            raise serializers.ValidationError("الرابط يجب أن يكون مسارًا داخل التطبيق يبدأ بـ /.")
        return v


class PlatformNoticeView(ControlView):
    def get_permissions(self):
        return [HasControlPerm.require("notifications.manage" if self.request.method == "POST" else "notifications.view")()]

    def get(self, request):
        qs = PlatformNotice.objects.select_related("sent_by", "environment")
        return Response(paginate(request, qs, notice_json))

    def post(self, request):
        ser = _NoticeSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if not webpush.enabled():
            return Response({"detail": "إشعارات الدفع غير مُفعّلة على الخادم (مفاتيح VAPID غير مضبوطة). لم يُرسل شيء.",
                             "code": "push_not_configured"}, status=409)
        env = None
        if d["audience"] in ("user", "users") and not d.get("user_ids"):
            raise invalid(user_ids="اختر مستخدمًا واحدًا على الأقل.")
        if d["audience"] == "user" and len(d.get("user_ids", [])) != 1:
            raise invalid(user_ids="اختر مستخدمًا واحدًا فقط.")
        if d["audience"] == "environment":
            env = Environment.objects.filter(pk=d.get("environment")).select_related("owner").first()
            if not env:
                raise invalid(environment="اختر بيئة صحيحة.")
        notice, err = pn.create_notice(sender=request.user, title=d["title"], body=d["body"], url=d["url"],
                                       audience=d["audience"], user_ids=d.get("user_ids"), environment=env)
        if err == "no_recipients":
            raise invalid(audience="لا يوجد مستلمون مؤهلون (حسابات مفعّلة) لهذا الاختيار.")
        if err == "too_many":
            raise invalid(audience=f"عدد المستلمين يتجاوز {pn.MAX_RECIPIENTS}. حدّد بيئة أو مجموعة أصغر.")
        audit.record(request, "notification.send", "platform_notice", notice.id, notice.title,
                     after={"audience": notice.audience, "recipients": notice.recipient_count})
        pn.deliver_queued(limit=pn.INLINE_LIMIT, notice=notice)
        return Response(notice_json(notice), status=201)


class _TemplateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    title = serializers.CharField(max_length=150)
    body = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    is_active = serializers.BooleanField(required=False)


def tpl_json(t):
    return {"id": t.id, "name": t.name, "title": t.title, "body": t.body, "is_active": t.is_active}


class TemplateListCreateView(ControlView):
    def get_permissions(self):
        return [HasControlPerm.require("notifications.manage" if self.request.method == "POST" else "notifications.view")()]

    def get(self, request):
        return Response([tpl_json(t) for t in NotificationTemplate.objects.all()])

    def post(self, request):
        ser = _TemplateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if NotificationTemplate.objects.filter(name__iexact=d["name"].strip()).exists():
            raise invalid(name="يوجد قالب بهذا الاسم.")
        t = NotificationTemplate.objects.create(name=d["name"].strip(), title=d["title"].strip(), body=d["body"],
                                                created_by=request.user)
        audit.record(request, "notification_template.create", "notification_template", t.id, t.name)
        return Response(tpl_json(t), status=201)


class TemplateDetailView(ControlView):
    perm = "notifications.manage"

    def patch(self, request, pk):
        t = get_object_or_404(NotificationTemplate, pk=pk)
        ser = _TemplateSerializer(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if "name" in d and NotificationTemplate.objects.filter(name__iexact=d["name"].strip()).exclude(pk=t.pk).exists():
            raise invalid(name="يوجد قالب بهذا الاسم.")
        before = {k: getattr(t, k) for k in d}
        for k, v in d.items():
            setattr(t, k, v.strip() if isinstance(v, str) else v)
        t.save()
        audit.record(request, "notification_template.update", "notification_template", t.id, t.name, *audit.diff(before, d))
        return Response(tpl_json(t))

    def delete(self, request, pk):
        t = get_object_or_404(NotificationTemplate, pk=pk)
        audit.record(request, "notification_template.delete", "notification_template", t.id, t.name)
        t.delete()
        return Response(status=204)


class RecipientSearchView(ControlView):
    """Picks recipients for a notice or ticket: matches name / email / phone, teachers and students only."""

    perm = ("notifications.manage", "tickets.create")

    def get(self, request):
        s = clean_search(request, "q")
        if len(s) < 2:
            return Response([])
        if request.query_params.get("kind") == "environment":
            return Response([{"id": e.id, "name": e.name, "owner": e.owner.name}
                             for e in Environment.objects.filter(Q(name__icontains=s) | Q(owner__name__icontains=s)).select_related("owner")[:10]])
        qs = User.objects.exclude(role="team").filter(Q(name__icontains=s) | Q(email__icontains=s) | Q(phone__icontains=s))[:10]
        return Response([{"id": u.id, "name": u.name, "role": u.role, "phone": u.phone, "email": u.email} for u in qs])
