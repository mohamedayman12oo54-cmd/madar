"""
Read-only figures for the guardian portal: exam scores, the lesson schedule, video watching, AI-quiz results,
a month-by-month trend and the optional class ranking. Everything is derived from records the child already owns; nothing here writes, and nothing exposes a
playable reference to a video (title and percent only).
"""
from collections import defaultdict
from datetime import date, timedelta

from django.db.models import Count
from django.db.models.functions import TruncMonth
from django.utils import timezone

from config.months import current_month
from content.models import ContentItem, VideoProgress
from evaluation.models import MonthlyRating
from learning import services as exam_services
from learning.models import Attempt, Exam
from scheduling.models import AttendanceRecord, Schedule, SessionInstance
from studentarea.models import QuizAttempt

EXAMS_SHOWN = 20
UPCOMING_SESSIONS = 5
VIDEOS_SHOWN = 15
QUIZZES_SHOWN = 10
TREND_MONTHS = 6


def _percent(part, whole):
    return round(100 * part / whole, 1) if whole else None


def class_schedule(enrollment):
    """When the child's lessons are: the weekly slots of each of their groups, and the next planned sessions.
    The times are the teacher's wall-clock times (Schedule.start_time is not timezone-aware on purpose)."""
    group_ids = [g.pk for g in enrollment.groups.all()]
    weekly = [{
        "group": sc.group.name, "weekday": sc.weekday, "weekday_label": sc.get_weekday_display(),
        "start_time": sc.start_time.strftime("%H:%M"),
        "end_time": sc.end_time.strftime("%H:%M") if sc.end_time else None,
    } for sc in Schedule.objects.filter(environment=enrollment.environment, group_id__in=group_ids)
        .select_related("group")]
    # Saturday-first, like the teacher's own schedule screen.
    order = [d for d, _ in Schedule.WEEKDAYS]
    weekly.sort(key=lambda r: (order.index(r["weekday"]), r["start_time"]))
    upcoming = (SessionInstance.objects
                .filter(environment=enrollment.environment, group_id__in=group_ids,
                        status__in=[SessionInstance.Status.PLANNED, SessionInstance.Status.OPEN],
                        scheduled_at__gte=timezone.now() - timedelta(hours=3))
                .select_related("group").order_by("scheduled_at")[:UPCOMING_SESSIONS])
    return {
        "weekly": weekly,
        "upcoming": [{"group": x.group.name, "scheduled_at": x.scheduled_at, "ends_at": x.ends_at,
                      "status": x.status} for x in upcoming],
    }


def exam_results(enrollment):
    """The child's exams, newest first, with the score that COUNTS (the best finished sitting - the same rule
    the student sees). Read-only: nothing is graded or closed from here, so a sitting whose clock ran out but
    was never opened again is reported as not submitted rather than finalised by a guardian's page view."""
    now = timezone.now()
    sittings = {}
    for a in Attempt.objects.filter(enrollment=enrollment).order_by("exam_id", "number"):
        sittings.setdefault(a.exam_id, []).append(a)

    rows = []
    for exam in Exam.visible_to(enrollment).order_by("-created_at", "-id")[:EXAMS_SHOWN]:
        mine = sittings.get(exam.pk, [])
        best = exam_services.best_attempt(mine)
        window = exam_services.availability(exam, now)
        if best:
            state = "finished"
        elif window == "upcoming":
            continue  # not started yet: nothing to report
        elif mine and not mine[-1].finished and mine[-1].deadline_at > now:
            state = "in_progress"
        elif window == "closed":
            state = "missed"
        else:
            state = "not_taken"
        row = {"id": exam.pk, "title": exam.title, "state": state, "closes_at": exam.closes_at,
               "score": None, "max_score": None, "percent": None}
        if best:
            row.update(score=best.score, max_score=best.max_score, percent=exam_services.percent(best))
        rows.append(row)

    done = [r["percent"] for r in rows if r["state"] == "finished"]
    return {
        "finished": len(done), "total": len(rows),
        "average_percent": round(sum(done) / len(done), 1) if done else None,
        "results": rows,
    }


def video_watching(enrollment):
    """Every video this child can watch (newest first) with how much of it they have watched."""
    videos = list(ContentItem.visible_to(enrollment).filter(kind=ContentItem.Kind.VIDEO)
                  .order_by("-published_at", "-id"))
    seen = {p.item_id: p for p in VideoProgress.objects.filter(enrollment=enrollment, item__in=videos)}
    rows = []
    for v in videos:
        p = seen.get(v.pk)
        rows.append({"id": v.pk, "title": v.title, "percent": p.percent if p else 0,
                     "completed": bool(p and p.completed), "last_watched_at": p.last_watched_at if p else None})
    return {
        "total": len(rows),
        "completed": sum(1 for r in rows if r["completed"]),
        "started": sum(1 for r in rows if r["percent"] > 0),
        "recent": rows[:VIDEOS_SHOWN],
    }


def quiz_results(enrollment):
    attempts = list(QuizAttempt.objects.filter(quiz__enrollment=enrollment)
                    .select_related("quiz").order_by("-submitted_at", "-id"))
    pcts = [100 * a.score / a.total for a in attempts if a.total]
    return {
        "taken": len(attempts),
        "average_percent": round(sum(pcts) / len(pcts), 1) if pcts else None,
        "recent": [{"title": a.quiz.content_title or "كويز", "score": a.score, "total": a.total,
                    "percent": _percent(a.score, a.total), "submitted_at": a.submitted_at}
                   for a in attempts[:QUIZZES_SHOWN]],
    }


def _months_back(n):
    """The last `n` calendar months as first-of-month dates, oldest first, ending with this month."""
    cur = current_month()
    idx = cur.year * 12 + cur.month - 1
    return [date((i // 12), (i % 12) + 1, 1) for i in range(idx - n + 1, idx + 1)]


def monthly_trend(enrollment):
    """One point per month for the last six: attendance %, average exam %, and the published rating (1-5)."""
    months = _months_back(TREND_MONTHS)
    since = months[0]

    present = defaultdict(int)
    total = defaultdict(int)
    for r in (AttendanceRecord.objects.filter(enrollment=enrollment, session__scheduled_at__date__gte=since)
              .annotate(m=TruncMonth("session__scheduled_at")).values("m", "status").annotate(n=Count("id"))):
        key = r["m"].date().replace(day=1)
        total[key] += r["n"]
        if r["status"] == AttendanceRecord.Status.PRESENT:
            present[key] += r["n"]

    # An exam counts in the month its best sitting was handed in.
    sittings = defaultdict(list)
    for a in Attempt.objects.filter(enrollment=enrollment, submitted_at__isnull=False,
                                    submitted_at__date__gte=since):
        sittings[a.exam_id].append(a)
    exam_pcts = defaultdict(list)
    for mine in sittings.values():
        best = exam_services.best_attempt(mine)
        if best and best.max_score:
            exam_pcts[timezone.localtime(best.submitted_at).date().replace(day=1)].append(exam_services.percent(best))

    ratings = dict(MonthlyRating.objects.filter(enrollment=enrollment, published_at__isnull=False, month__gte=since)
                   .values_list("month", "value"))

    return [{
        "month": m.strftime("%Y-%m"),
        "attendance_percent": _percent(present[m], total[m]),
        "exam_percent": round(sum(exam_pcts[m]) / len(exam_pcts[m]), 1) if exam_pcts[m] else None,
        "rating": ratings.get(m),
    } for m in months]


# A ranking among very few classmates points at individuals ("last of 2"), so it is not shown until enough
# classmates have a score to hide behind.
MIN_RANKED = 5


def group_rank(enrollment):
    """Where the child stands among classmates by exam average, or None when the teacher has not switched
    the ranking on. Classmates = active students who share at least one group with the child. Only the
    child's own position and the head-count leave this function: never a name, never anyone else's score."""
    from academics.models import Enrollment

    from .models import GuardianAlertSettings

    cfg = GuardianAlertSettings.objects.filter(environment_id=enrollment.environment_id).first()
    if cfg is None or not cfg.show_rank:
        return None

    group_ids = [g.pk for g in enrollment.groups.all()]
    mates = set(Enrollment.objects.filter(environment_id=enrollment.environment_id, is_active=True,
                                          groups__id__in=group_ids).values_list("pk", flat=True))
    mates.add(enrollment.pk)

    # Each classmate's mean of their BEST percent per exam they sat.
    best = {}
    for a in (Attempt.objects.filter(enrollment_id__in=mates, submitted_at__isnull=False, max_score__gt=0)
              .only("enrollment_id", "exam_id", "score", "max_score")):
        key = (a.enrollment_id, a.exam_id)
        pct = 100 * (a.score or 0) / a.max_score
        if pct > best.get(key, -1):
            best[key] = pct
    per_student = defaultdict(list)
    for (enrollment_id, _), pct in best.items():
        per_student[enrollment_id].append(pct)
    averages = {pk: sum(v) / len(v) for pk, v in per_student.items()}

    mine = averages.get(enrollment.pk)
    if mine is None or len(averages) < MIN_RANKED:
        return {"position": None, "of": None, "basis": "exam_average"}
    # Ties share a position ("1, 2, 2, 4").
    position = 1 + sum(1 for v in averages.values() if round(v, 1) > round(mine, 1))
    return {"position": position, "of": len(averages), "basis": "exam_average"}
