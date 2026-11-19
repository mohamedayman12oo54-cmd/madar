"""System health, background operations, audit log and settings. Health is built only from signals the
application can actually observe: a live database round-trip, a live cache round-trip, queue contents and the
JobRun records the workers write. Where there is no record the page says "never recorded" — it does not invent
a green light."""
import time
from datetime import timedelta

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.db.models import Count, Q
from rest_framework import serializers
from rest_framework.response import Response

from accounts.models import PendingAuth
from ai.models import AIOperation
from notifications import webpush
from notifications.models import Notification

from . import audit
from .access import HasControlPerm
from .common import ControlView, id_param, date_param, clean_search, csv_response, invalid, iso, paginate
from .jobs import MONITORED_JOBS
from .models import AuditLog, JobRun, PlatformSetting
from .settings_registry import GROUP_LABELS, REGISTRY, all_settings, get_setting, validate_value
from .support_services import now
from .users import audit_row


def _check_db():
    t = time.monotonic()
    try:
        with connection.cursor() as c:
            c.execute("SELECT 1")
            c.fetchone()
        return {"ok": True, "latency_ms": int((time.monotonic() - t) * 1000)}
    except Exception:
        return {"ok": False, "latency_ms": None}


def _check_cache():
    try:
        cache.set("control-health", "1", 5)
        return {"ok": cache.get("control-health") == "1"}
    except Exception:
        return {"ok": False}


def job_status(name, last, interval_min):
    if last is None:
        return "never"
    if last.status == "failed":
        return "failed"
    if now() - last.finished_at > timedelta(minutes=interval_min * 2):
        return "quiet"
    return "ok"


def jobs_summary():
    day = now() - timedelta(hours=24)
    out = []
    for name, (label, interval) in MONITORED_JOBS.items():
        runs = JobRun.objects.filter(name=name)
        last = runs.first()
        last_error = runs.filter(status="failed").first()
        out.append({
            "name": name, "label": label, "expected_every_minutes": interval, "status": job_status(name, last, interval),
            "last_run": None if last is None else {
                "at": iso(last.started_at), "status": last.status, "duration_ms": last.duration_ms,
                "processed": last.processed, "failed_items": last.failed_items, "error": last.error},
            "runs_24h": runs.filter(started_at__gte=day).count(),
            "failed_runs_24h": runs.filter(started_at__gte=day, status="failed").count(),
            "last_error": None if last_error is None else {"at": iso(last_error.started_at), "error": last_error.error},
        })
    return out


class HealthView(ControlView):
    perm = "system.view"

    def get(self, request):
        day = now() - timedelta(hours=24)
        pending = Notification.objects.filter(delivery_status="pending")
        oldest = pending.order_by("created_at").values_list("created_at", flat=True).first()
        stuck_cut = now() - timedelta(minutes=15)
        ai_pending = AIOperation.objects.filter(status="pending")
        ai_oldest = ai_pending.order_by("created_at").values_list("created_at", flat=True).first()
        db, cache_state = _check_db(), _check_cache()
        jobs = jobs_summary()
        problems = []
        if not db["ok"]:
            problems.append("db")
        if not cache_state["ok"]:
            problems.append("cache")
        if any(j["status"] == "failed" for j in jobs):
            problems.append("jobs")
        backlog_min = int(get_setting("notifications.pending_minutes"))
        notif_backlog = bool(oldest and now() - oldest > timedelta(minutes=backlog_min))
        if notif_backlog:
            problems.append("notifications")
        return Response({
            "checked_at": iso(now()),
            "overall": "degraded" if problems else "ok", "problems": problems,
            "api": {"ok": True, "note": "هذا الطلب نفسه وصل إلى الخادم."},
            "database": db, "cache": cache_state,
            "notifications": {
                "pending": pending.count(), "oldest_pending_at": iso(oldest), "backlog": notif_backlog,
                "failed_24h": Notification.objects.filter(delivery_status="failed", created_at__gte=day).count(),
                "push_configured": webpush.enabled(), "dispatch_mode": settings.NOTIFICATION_WORKER_MODE},
            "ai": {
                "pending": ai_pending.count(), "oldest_pending_at": iso(ai_oldest),
                "processing": AIOperation.objects.filter(status="processing").count(),
                "stuck_processing": AIOperation.objects.filter(status="processing", started_at__lt=stuck_cut).count(),
                "failed_24h": AIOperation.objects.filter(status="failed", created_at__gte=day).count(),
                "provider": settings.AI_PROVIDER, "worker_mode": settings.AI_WORKER_MODE},
            "jobs": jobs,
            "recent_errors": {
                "jobs": [{"name": j.name, "at": iso(j.started_at), "error": j.error}
                         for j in JobRun.objects.filter(status="failed")[:8]],
                "ai": [{"id": o.id, "kind": o.kind, "at": iso(o.created_at), "error": o.error}
                       for o in AIOperation.objects.filter(status="failed")[:5]],
                "notifications": [{"id": n.id, "at": iso(n.created_at), "error": n.delivery_error}
                                  for n in Notification.objects.filter(delivery_status="failed")[:5]],
            },
            "housekeeping": {"pending_auth_rows": PendingAuth.objects.count()},
        })


class JobRunListView(ControlView):
    perm = "system.view"

    def get(self, request):
        qs = JobRun.objects.all()
        if request.query_params.get("name"):
            qs = qs.filter(name=request.query_params["name"])
        if request.query_params.get("status"):
            qs = qs.filter(status=request.query_params["status"])
        page = paginate(request, qs, lambda j: {
            "id": j.id, "name": j.name, "label": MONITORED_JOBS.get(j.name, (j.name,))[0], "status": j.status,
            "started_at": iso(j.started_at), "duration_ms": j.duration_ms, "processed": j.processed,
            "failed_items": j.failed_items, "error": j.error})
        page["summary"] = jobs_summary()
        return Response(page)


# ------------------------------------------------------------------ audit
def filtered_audit(request):
    q = request.query_params
    qs = AuditLog.objects.all()
    if (_actor := id_param(request, "actor")) is not None:
        qs = qs.filter(actor_id=_actor)
    if q.get("action"):
        qs = qs.filter(action__startswith=q["action"])
    if q.get("entity_type"):
        qs = qs.filter(entity_type=q["entity_type"])
    if q.get("entity_id"):
        qs = qs.filter(entity_id=q["entity_id"])
    if q.get("hide_views") == "1":
        qs = qs.exclude(action="view")
    if (_from := date_param(request, "from")):
        qs = qs.filter(created_at__date__gte=_from)
    if (_to := date_param(request, "to")):
        qs = qs.filter(created_at__date__lte=_to)
    if s := clean_search(request):
        qs = qs.filter(Q(entity_label__icontains=s) | Q(actor_label__icontains=s) | Q(note__icontains=s) | Q(action__icontains=s))
    return qs


class AuditListView(ControlView):
    perm = "audit.view"

    def get(self, request):
        qs = filtered_audit(request)
        if request.query_params.get("export") == "csv":
            return csv_response("audit-log.csv", ["الوقت", "المنفّذ", "الإجراء", "نوع الكيان", "الكيان", "قبل", "بعد", "ملاحظة", "IP"],
                                [[iso(a.created_at), a.actor_label, a.action, a.entity_type, a.entity_label, str(a.before),
                                  str(a.after), a.note, a.ip_address or ""] for a in qs[:5000]])
        page = paginate(request, qs, audit_row)
        page["filters"] = {
            "actions": list(AuditLog.objects.values_list("action", flat=True).distinct().order_by("action")),
            "entity_types": list(AuditLog.objects.values_list("entity_type", flat=True).distinct().order_by("entity_type")),
            # one entry per person even if their display name changed over time (the latest label wins)
            "actors": [{"id": i, "name": n} for i, n in dict(
                AuditLog.objects.exclude(actor__isnull=True).order_by("created_at")
                .values_list("actor_id", "actor_label")).items()][:100],
        }
        return Response(page)


# ------------------------------------------------------------------ settings
def readonly_settings():
    jwt = settings.SIMPLE_JWT
    rates = settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"]
    return [
        {"key": "session.access_minutes", "group": "session", "label": "مدة رمز الدخول",
         "description": "يتجدّد تلقائيًا أثناء استخدام التطبيق. يُضبط على مستوى النشر.", "value": int(jwt["ACCESS_TOKEN_LIFETIME"].total_seconds() // 60), "unit": "دقيقة"},
        {"key": "session.refresh_days", "group": "session", "label": "مدة الجلسة دون استخدام",
         "description": "أقصى مدة تبقى فيها الجلسة صالحة بعد آخر تجديد.", "value": jwt["REFRESH_TOKEN_LIFETIME"].days, "unit": "يوم"},
        {"key": "security.login_rate", "group": "security", "label": "حد محاولات الدخول",
         "description": "لكل عنوان IP. يمنع التخمين الآلي لكلمات المرور.", "value": rates.get("login"), "unit": ""},
        {"key": "security.otp_ttl", "group": "security", "label": "صلاحية رمز التحقق",
         "description": "المدة التي يبقى فيها رمز OTP صالحًا.", "value": PendingAuth.OTP_TTL_SECONDS // 60, "unit": "دقيقة"},
        {"key": "security.otp_attempts", "group": "security", "label": "محاولات رمز التحقق",
         "description": "عدد التخمينات المسموحة لكل رمز.", "value": PendingAuth.MAX_ATTEMPTS, "unit": ""},
        {"key": "platform.ai_provider", "group": "general", "label": "مزوّد الذكاء الاصطناعي",
         "description": "قيمة التشغيل الحالية (لا تُعرض المفاتيح).", "value": settings.AI_PROVIDER, "unit": ""},
    ]


class SettingsView(ControlView):
    def get_permissions(self):
        return [HasControlPerm.require("settings.manage" if self.request.method == "PATCH" else "settings.view")()]

    def get(self, request):
        vals = all_settings()
        return Response({
            "editable": [{"key": k, "group": r[0], "group_label": GROUP_LABELS[r[0]], "label": r[1], "description": r[2],
                          "value": vals[k], "default": r[3], "min": r[4], "max": r[5]} for k, r in REGISTRY.items()],
            "readonly": readonly_settings(),
        })

    def patch(self, request):
        data = request.data
        if not isinstance(data, dict) or not data:
            raise invalid(detail="لا توجد إعدادات للحفظ.")
        errors, clean = {}, {}
        for k, v in data.items():
            if k not in REGISTRY:
                errors[k] = ["إعداد غير معروف."]
                continue
            try:
                clean[k] = validate_value(k, v)
            except ValueError as exc:
                errors[k] = [str(exc)]
        if errors:
            raise serializers.ValidationError(errors)
        before = {k: get_setting(k) for k in clean}
        changed = {k: v for k, v in clean.items() if before[k] != v}
        for k, v in changed.items():
            PlatformSetting.objects.update_or_create(key=k, defaults={"value": v, "updated_by": request.user})
        if changed:
            audit.record(request, "settings.update", "settings", "", "إعدادات المنصة",
                         {k: before[k] for k in changed}, changed)
        return self.get(request)
