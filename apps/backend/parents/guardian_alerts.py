"""
Automatic warnings to guardians (opt-in per teacher, see GuardianAlertSettings).

Three rules, each producing at most ONE message per child per period, however many times the worker runs:
  * absences in the current month reached the teacher's threshold   -> key "absent:YYYY-MM"
  * this month's fee still unpaid from the teacher's chosen day     -> key "unpaid:YYYY-MM"
  * the child's best score in an exam is below the teacher's limit  -> key "exam:<exam id>"

Idempotence is the database's job (unique constraint on enrollment + key), so two workers racing cannot
double-send. Only enrollments with a guardian phone are considered: there is nobody to read the message otherwise.
"""
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.db.models import Count
from django.utils import timezone

from academics.models import Enrollment
from config.months import current_month, month_bounds
from financials.models import MonthlyPayment
from learning import services as exam_services
from learning.models import Attempt
from scheduling.models import AttendanceRecord

from .models import GuardianAlertSettings, GuardianMessage

# Exam results older than this are not re-examined on every run (they were handled when they were new).
EXAM_LOOKBACK = timedelta(days=30)


def _send(environment_id, enrollment, key, title, body):
    try:
        with transaction.atomic():
            GuardianMessage.objects.create(
                environment_id=environment_id, enrollment=enrollment, kind=GuardianMessage.Kind.WARNING,
                title=title, body=body, auto_key=key)
        return 1
    except IntegrityError:  # already sent for this period
        return 0


def _absences(cfg, by_id, first, nxt):
    if not cfg.absence_threshold:
        return 0
    rows = (AttendanceRecord.objects
            .filter(environment_id=cfg.environment_id, enrollment_id__in=list(by_id),
                    status=AttendanceRecord.Status.ABSENT, session__scheduled_at__date__gte=first,
                    session__scheduled_at__date__lt=nxt)
            .values("enrollment_id").annotate(n=Count("id")).filter(n__gte=cfg.absence_threshold))
    sent = 0
    for r in rows:
        e = by_id[r["enrollment_id"]]
        sent += _send(cfg.environment_id, e, f"absent:{first:%Y-%m}", "تنبيه غياب",
                      f"غاب {e.display_name} {r['n']} حصص هذا الشهر (حد التنبيه {cfg.absence_threshold}).")
    return sent


def _unpaid(cfg, by_id, first):
    if not cfg.unpaid_after_day or timezone.localdate().day < cfg.unpaid_after_day:
        return 0
    rows = MonthlyPayment.objects.filter(environment_id=cfg.environment_id, month=first)
    paid = set(rows.filter(status=MonthlyPayment.Status.PAID).values_list("enrollment_id", flat=True))
    amounts = dict(rows.values_list("enrollment_id", "amount"))
    sent = 0
    for pk, e in by_id.items():
        if pk in paid:
            continue
        amount = amounts.get(pk, e.grade.fee_amount)
        sent += _send(cfg.environment_id, e, f"unpaid:{first:%Y-%m}", "تذكير بمصروفات الشهر",
                      f"لم يُسجَّل دفع مصروفات شهر {first:%Y-%m} للطالب {e.display_name} حتى الآن. "
                      f"المبلغ: {amount}.")
    return sent


def _exams(cfg, by_id):
    if not cfg.exam_percent_below:
        return 0
    sittings = {}
    recent = Attempt.objects.filter(
        exam__environment_id=cfg.environment_id, enrollment_id__in=list(by_id), submitted_at__isnull=False,
        submitted_at__gte=timezone.now() - EXAM_LOOKBACK).select_related("exam")
    for a in recent.order_by("exam_id", "enrollment_id", "number"):
        sittings.setdefault((a.exam_id, a.enrollment_id), []).append(a)
    sent = 0
    for (exam_id, enrollment_id), mine in sittings.items():
        best = exam_services.best_attempt(mine)
        if best is None or not best.max_score or exam_services.percent(best) >= cfg.exam_percent_below:
            continue
        e = by_id[enrollment_id]
        sent += _send(cfg.environment_id, e, f"exam:{exam_id}", "درجة منخفضة في امتحان",
                      f"حصل {e.display_name} على {best.score:g} من {best.max_score:g} "
                      f"({exam_services.percent(best):g}%) في امتحان «{best.exam.title}».")
    return sent


def run_for(cfg):
    """Evaluate every rule for one teacher. Returns how many NEW messages were written."""
    by_id = {e.pk: e for e in Enrollment.objects.filter(environment_id=cfg.environment_id, is_active=True)
             .exclude(parent_phone="").select_related("grade", "student")}
    if not by_id:
        return 0
    first, nxt = month_bounds(current_month())
    return _absences(cfg, by_id, first, nxt) + _unpaid(cfg, by_id, first) + _exams(cfg, by_id)


def run_all():
    return sum(run_for(cfg) for cfg in GuardianAlertSettings.objects.filter(enabled=True))
