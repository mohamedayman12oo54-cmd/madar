"""The Control Center home: KPIs with period-over-period comparison, charts, the live activity feed and the
"needs attention" list. Every number is a query on the real tables; a section the member has no permission for
is simply absent from the response (the page draws only what it receives)."""
from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework.response import Response

from accounts.models import User
from ai.models import AIOperation
from billing.models import PaymentAttempt, ProviderEvent
from environments.models import Environment
from notifications.models import Notification
from scheduling.models import AttendanceRecord

from .access import can
from .common import ControlView, as_id, clean_search, iso, parse_range, pct_change, series
from .jobs import MONITORED_JOBS
from .models import AuditLog, JobRun, Ticket
from .settings_registry import get_setting
from .support_services import is_overdue, now
from .users import with_activity

PA = PaymentAttempt.Status


def kpi(key, value, current=None, previous=None, link=None, tone=None):
    d = {"key": key, "value": value, "link": link}
    if current is not None:
        d["period"] = {"current": current, "previous": previous, "change_pct": pct_change(current, previous)}
    if tone:
        d["tone"] = tone
    return d


def people():
    return User.objects.exclude(role="team")


def new_between(qs, field, a, b):
    return qs.filter(**{f"{field}__gte": a, f"{field}__lt": b}).count()


class OverviewView(ControlView):
    perm = "overview.view"

    def get(self, request):
        start, end, prev, label = parse_range(request, "30d")
        kpis, charts = [], {}

        if can(request, "users.view"):
            active_now = with_activity(people()).filter(last_activity__gte=start, last_activity__lt=end).count()
            active_before = with_activity(people()).filter(last_activity__gte=prev, last_activity__lt=start).count()
            kpis += [
                kpi("total_users", people().count(), new_between(people(), "date_joined", start, end),
                    new_between(people(), "date_joined", prev, start), "/team/users"),
                kpi("active_users", active_now, active_now, active_before, "/team/users"),
                kpi("total_teachers", people().filter(role="teacher").count(),
                    new_between(people().filter(role="teacher"), "date_joined", start, end),
                    new_between(people().filter(role="teacher"), "date_joined", prev, start), "/team/teachers"),
                kpi("total_students", people().filter(role="student").count(),
                    new_between(people().filter(role="student"), "date_joined", start, end),
                    new_between(people().filter(role="student"), "date_joined", prev, start), "/team/students"),
            ]
            if can(request, "environments.view"):
                kpis.append(kpi("total_environments", Environment.objects.count(),
                                new_between(Environment.objects, "created_at", start, end),
                                new_between(Environment.objects, "created_at", prev, start), "/team/environments"))
            before = people().filter(date_joined__lt=start).count()
            daily = series(people(), "date_joined", start, end)
            running, growth = before, []
            for p in daily:
                running += p["value"]
                growth.append({"date": p["date"], "value": running})
            charts["user_growth"] = growth
            charts["teacher_registrations"] = series(people().filter(role="teacher"), "date_joined", start, end)
            charts["student_registrations"] = series(people().filter(role="student"), "date_joined", start, end)
            charts["daily_activity"] = {
                "attendance": series(AttendanceRecord.objects.all(), "created_at", start, end),
                "notifications": series(Notification.objects.all(), "created_at", start, end),
                "ai": series(AIOperation.objects.all(), "created_at", start, end),
                "tickets": series(Ticket.objects.all(), "created_at", start, end),
            }

        if can(request, "tickets.view"):
            active = Ticket.objects.filter(status__in=Ticket.ACTIVE)
            kpis += [
                kpi("open_tickets", active.count(), new_between(Ticket.objects, "created_at", start, end),
                    new_between(Ticket.objects, "created_at", prev, start), "/team/support/tickets?active=1"),
                kpi("unassigned_tickets", active.filter(assignee__isnull=True).count(), link="/team/support/unassigned",
                    tone="warn"),
                kpi("critical_complaints", active.filter(kind="complaint", priority="critical").count(),
                    link="/team/support/complaints", tone="bad"),
            ]
            charts["ticket_trends"] = {"created": series(Ticket.objects.all(), "created_at", start, end),
                                       "resolved": series(Ticket.objects.all(), "resolved_at", start, end)}
            charts["ticket_resolution"] = list(Ticket.objects.filter(created_at__gte=start, created_at__lt=end)
                                               .values("status").annotate(count=Count("id")))

        if can(request, "ai.view"):
            ops = AIOperation.objects.filter(created_at__gte=start, created_at__lt=end)
            pops = AIOperation.objects.filter(created_at__gte=prev, created_at__lt=start)
            kpis += [
                kpi("ai_success", ops.filter(status="completed").count(), ops.filter(status="completed").count(),
                    pops.filter(status="completed").count(), "/team/ai"),
                kpi("ai_failed", ops.filter(status="failed").count(), ops.filter(status="failed").count(),
                    pops.filter(status="failed").count(), "/team/ai?status=failed", tone="bad"),
            ]
            charts["ai"] = {"success": series(AIOperation.objects.filter(status="completed"), "created_at", start, end),
                            "failed": series(AIOperation.objects.filter(status="failed"), "created_at", start, end)}

        if can(request, "finance.view"):
            att = PaymentAttempt.objects.filter(created_at__gte=start, created_at__lt=end)
            patt = PaymentAttempt.objects.filter(created_at__gte=prev, created_at__lt=start)
            kpis += [
                kpi("payments_success", att.filter(status=PA.SUCCEEDED).count(), att.filter(status=PA.SUCCEEDED).count(),
                    patt.filter(status=PA.SUCCEEDED).count(), "/team/finance/transactions?status=succeeded"),
                kpi("payments_pending", PaymentAttempt.objects.filter(status__in=PaymentAttempt.NON_TERMINAL_STATUSES).count(),
                    link="/team/finance/transactions?status=pending", tone="warn"),
            ]
            charts["finance"] = {
                "succeeded": series(PaymentAttempt.objects.filter(status=PA.SUCCEEDED), "created_at", start, end),
                "failed": series(PaymentAttempt.objects.filter(status=PA.FAILED), "created_at", start, end),
            }

        return Response({"range": label, "from": iso(start), "to": iso(end), "kpis": kpis, "charts": charts,
                         "attention": attention(request), "activity": activity(request)})


# ------------------------------------------------------------------ attention
def attention(request):
    items = []
    day = now() - timedelta(hours=24)
    if can(request, "tickets.view"):
        active = Ticket.objects.filter(status__in=Ticket.ACTIVE)
        crit = active.filter(kind="complaint", priority__in=("critical", "high"))
        if n := crit.count():
            items.append({"key": "critical_complaints", "severity": "high", "count": n, "link": "/team/support/complaints",
                          "samples": [{"label": t.number + " · " + t.subject, "link": f"/team/support/tickets/{t.id}"}
                                      for t in crit.order_by("created_at")[:3]]})
        if n := Ticket.objects.filter(status__in=Ticket.WORKING, due_at__lt=now()).count():
            items.append({"key": "overdue_tickets", "severity": "high", "count": n, "link": "/team/support/tickets?overdue=1"})
        stale = now() - timedelta(hours=int(get_setting("tickets.stale_hours")))
        if n := active.filter(awaiting_team=True, last_activity_at__lt=stale).exclude(status="waiting_for_user").count():
            items.append({"key": "waiting_too_long", "severity": "medium", "count": n,
                          "link": "/team/support/tickets?response=awaiting_team"})
        if n := active.filter(assignee__isnull=True).count():
            items.append({"key": "unassigned_tickets", "severity": "medium", "count": n, "link": "/team/support/unassigned"})
    if can(request, "finance.view"):
        since = now() - timedelta(days=int(get_setting("payments.attention_days")))
        n = PaymentAttempt.objects.filter(status__in=(PA.FAILED, PA.UNKNOWN), created_at__gte=since).count()
        if n:
            items.append({"key": "failed_payments", "severity": "high", "count": n, "link": "/team/finance/issues"})
        n = ProviderEvent.objects.filter(processing_status="failed_to_apply", received_at__gte=since).count()
        if n:
            items.append({"key": "payment_verification", "severity": "high", "count": n, "link": "/team/finance/issues"})
    if can(request, "ai.view"):
        n = AIOperation.objects.filter(status="failed", created_at__gte=day).count()
        if n >= int(get_setting("ai.repeated_failures")):
            items.append({"key": "ai_failures", "severity": "high", "count": n, "link": "/team/ai?status=failed"})
    if can(request, "system.view"):
        bad = JobRun.objects.filter(status="failed", started_at__gte=day)
        if n := bad.count():
            items.append({"key": "job_failures", "severity": "high", "count": n, "link": "/team/system/jobs"})
        pending_cut = now() - timedelta(minutes=int(get_setting("notifications.pending_minutes")))
        if n := Notification.objects.filter(delivery_status="pending", created_at__lt=pending_cut).count():
            items.append({"key": "notification_backlog", "severity": "medium", "count": n, "link": "/team/system/health"})
    return items


# ------------------------------------------------------------------ activity
def activity(request, limit=25):
    feed = []
    if can(request, "users.view"):
        for u in people().order_by("-date_joined")[:8]:
            feed.append({"kind": "user", "text": f"{'معلّم' if u.role == 'teacher' else 'طالب'} جديد: {u.name or '—'}",
                         "at": u.date_joined, "link": f"/team/users/{u.id}"})
    if can(request, "tickets.view"):
        for t in Ticket.objects.select_related("category").order_by("-created_at")[:8]:
            feed.append({"kind": "ticket", "text": f"{'شكوى' if t.kind == 'complaint' else 'تذكرة'} جديدة {t.number}: {t.subject}",
                         "at": t.created_at, "link": f"/team/support/tickets/{t.id}"})
        from .models import TicketEvent

        for e in TicketEvent.objects.filter(kind__in=("assigned", "status", "reopened")).select_related("ticket").order_by("-created_at")[:10]:
            txt = {"assigned": f"إسناد {e.ticket.number} إلى {e.to_value or 'لا أحد'}",
                   "status": f"{e.ticket.number}: الحالة → {e.to_value}", "reopened": f"إعادة فتح {e.ticket.number}"}[e.kind]
            feed.append({"kind": "ticket_event", "text": txt, "at": e.created_at, "link": f"/team/support/tickets/{e.ticket_id}"})
    if can(request, "finance.view"):
        for p in PaymentAttempt.objects.order_by("-updated_at")[:6]:
            feed.append({"kind": "payment", "text": f"عملية دفع {p.get_status_display()} — {p.amount_minor_units / 100:.2f} {p.currency}",
                         "at": p.updated_at, "link": "/team/finance/transactions"})
    if can(request, "ai.view"):
        for op in AIOperation.objects.filter(status="failed").order_by("-created_at")[:6]:
            feed.append({"kind": "ai", "text": f"فشلت عملية ذكاء اصطناعي ({op.get_kind_display()})", "at": op.created_at,
                         "link": f"/team/ai/{op.id}"})
    if can(request, "audit.view"):
        for a in AuditLog.objects.exclude(action="view").order_by("-created_at")[:10]:
            feed.append({"kind": "admin", "text": f"{a.actor_label or 'النظام'}: {a.action} — {a.entity_label}", "at": a.created_at,
                         "link": "/team/audit"})
    feed.sort(key=lambda i: i["at"], reverse=True)
    return [{**i, "at": iso(i["at"])} for i in feed[:limit]]


class ActivityFeedView(ControlView):
    """Polled by the overview to keep the feed live."""

    perm = "overview.view"

    def get(self, request):
        return Response({"activity": activity(request), "attention": attention(request)})


class SearchView(ControlView):
    perm = "overview.view"

    def get(self, request):
        s = clean_search(request, "q")
        out = {"users": [], "tickets": [], "environments": []}
        if len(s) < 2:
            return Response(out)
        if can(request, "users.view"):
            cond = Q(name__icontains=s) | Q(email__icontains=s) | Q(phone__icontains=s)
            out["users"] = [{"id": u.id, "name": u.name, "role": u.role, "link": f"/team/users/{u.id}"}
                            for u in people().filter(cond)[:5]]
        if can(request, "tickets.view"):
            digits = s.upper().replace("MDR-", "").lstrip("0")
            cond = Q(subject__icontains=s) | Q(requester_name__icontains=s)
            if (tid := as_id(digits)) is not None:
                cond |= Q(pk=tid)
            out["tickets"] = [{"id": t.id, "name": f"{t.number} · {t.subject}", "link": f"/team/support/tickets/{t.id}"}
                              for t in Ticket.objects.filter(cond)[:5]]
        if can(request, "environments.view"):
            out["environments"] = [{"id": e.id, "name": e.name, "link": f"/team/environments/{e.id}"}
                                   for e in Environment.objects.filter(Q(name__icontains=s) | Q(owner__name__icontains=s))[:5]]
        return Response(out)
