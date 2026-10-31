"""The exam engine. Every rule that decides a student's result lives here, server-side."""
import random
from datetime import datetime
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Answer, Attempt, AttemptGrant, Choice, Exam

# Events the browser may report. Anything else is ignored (never trust the client's vocabulary).
VIOLATION_TYPES = {"blur", "hidden", "fullscreen_exit", "copy", "paste", "contextmenu", "print", "shortcut"}
# One alt-tab fires blur AND hidden (and often leaves full screen too): reports of the same FAMILY within this
# window count once, so a single "leaving" is a single warning, not three.
LEAVE_FAMILY = {"blur": "leave", "hidden": "leave", "fullscreen_exit": "leave"}
DEDUPE_SECONDS = 5
LOG_CAP = 100


class ExamClosed(Exception):
    def __init__(self, message, code="closed"):
        super().__init__(message)
        self.message, self.code = message, code


def availability(exam: Exam, now=None):
    now = now or timezone.now()
    if exam.published_at is None:
        return "hidden"
    if exam.opens_at and now < exam.opens_at:
        return "upcoming"
    if exam.closes_at and now >= exam.closes_at:
        return "closed"
    return "open"


def finalize(attempt: Attempt, reason: str) -> Attempt:
    """Grade and close an attempt. Idempotent: a closed attempt is returned untouched."""
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update().get(pk=attempt.pk)
        if attempt.submitted_at:
            return attempt
        correct = set(Choice.objects.filter(question__exam_id=attempt.exam_id, is_correct=True)
                      .values_list("pk", flat=True))
        points = {q.pk: q.points for q in attempt.exam.questions.all()}
        score = sum(points[a.question_id] for a in attempt.answers.all()
                    if a.choice_id in correct and a.question_id in points)
        attempt.score = float(score)
        attempt.max_score = float(sum(points.values()))
        attempt.submitted_at = timezone.now()
        attempt.end_reason = reason
        attempt.save(update_fields=["score", "max_score", "submitted_at", "end_reason"])
    return attempt


def expire_if_due(attempt: Attempt) -> Attempt:
    if not attempt.submitted_at and timezone.now() >= attempt.deadline_at:
        return finalize(attempt, Attempt.End.TIME)
    return attempt


def latest_attempt(exam, enrollment):
    return Attempt.objects.select_related("exam").filter(exam=exam, enrollment=enrollment).order_by("-number").first()


def open_grant(exam, enrollment):
    return AttemptGrant.objects.filter(exam=exam, enrollment=enrollment, used_by__isnull=True).first()


def best_attempt(attempts):
    """The finished attempt that counts: highest score; on a tie the most recent one."""
    done = [a for a in attempts if a.submitted_at]
    return max(done, key=lambda a: (a.score or 0, a.number)) if done else None


def percent(attempt):
    return round(100 * attempt.score / attempt.max_score, 1) if attempt and attempt.max_score else 0


def start_or_resume(exam: Exam, enrollment, retake=False) -> Attempt:
    """Start the student's first sitting, resume an unfinished one, or (retake=True) start the next sitting the
    teacher allowed. Without `retake`, a finished exam just returns the finished attempt."""
    try:
        return _start(exam, enrollment, retake)
    except IntegrityError:  # two parallel taps created the same attempt number: use the one that won
        winner = latest_attempt(exam, enrollment)
        if winner:
            return expire_if_due(winner)
        raise


def _start(exam, enrollment, retake):
    now = timezone.now()
    with transaction.atomic():
        existing = Attempt.objects.select_for_update().filter(exam=exam, enrollment=enrollment).order_by("-number").first()
        if existing:
            existing = expire_if_due(existing)
            if not existing.finished or not retake:
                return existing
        grant = AttemptGrant.objects.select_for_update().filter(
            exam=exam, enrollment=enrollment, used_by__isnull=True).first()
        if existing and not grant:
            raise ExamClosed("لا توجد لديك محاولة أخرى في هذا الامتحان. تواصل مع معلمك.", "no_retake")
        if not grant:  # a first sitting follows the exam's opening window; a re-opened one does not
            state = availability(exam, now)
            if state != "open":
                raise ExamClosed({"upcoming": "لم يبدأ الامتحان بعد.", "closed": "انتهى موعد هذا الامتحان."}
                                 .get(state, "الامتحان غير متاح."), state)
        qs = list(exam.questions.prefetch_related("choices"))
        if not qs:
            raise ExamClosed("هذا الامتحان لا يحتوي على أسئلة.", "empty")
        order = [q.pk for q in qs]
        if exam.shuffle_questions:
            random.shuffle(order)
        choice_orders = {}
        for q in qs:
            ids = [c.pk for c in q.choices.all()]
            if exam.shuffle_choices:
                random.shuffle(ids)
            choice_orders[str(q.pk)] = ids
        deadline = now + timedelta(minutes=exam.duration_minutes)
        if exam.closes_at and not grant:
            deadline = min(deadline, exam.closes_at)
        attempt = Attempt.objects.create(exam=exam, enrollment=enrollment, deadline_at=deadline,
                                         number=(existing.number + 1) if existing else 1,
                                         question_order=order, choice_orders=choice_orders)
        if grant:
            grant.used_by = attempt
            grant.save(update_fields=["used_by"])
        return attempt


def reopen(exam: Exam, enrollment, by=None) -> AttemptGrant:
    """Teacher action: let this student sit the exam once more. Idempotent while a grant is still unused."""
    with transaction.atomic():
        pending = AttemptGrant.objects.select_for_update().filter(
            exam=exam, enrollment=enrollment, used_by__isnull=True).first()
        if pending:
            return pending
        latest = Attempt.objects.select_for_update().filter(exam=exam, enrollment=enrollment).order_by("-number").first()
        if latest:
            latest = expire_if_due(latest)
            if not latest.finished:
                raise ExamClosed("الطالب يحل الامتحان الآن. انتظر حتى يسلّمه أو ينتهي وقته.", "in_progress")
        elif availability(exam) == "open":
            raise ExamClosed("الامتحان متاح لهذا الطالب أصلًا ولم يبدأه بعد.", "already_open")
        return AttemptGrant.objects.create(exam=exam, enrollment=enrollment, granted_by=by)


def question_payload(attempt: Attempt, index: int):
    """ONE question for this student, in HER order, with choices (no correctness) — nothing else."""
    qid = attempt.question_order[index]
    q = attempt.exam.questions.prefetch_related("choices").get(pk=qid)
    by_id = {c.pk: c for c in q.choices.all()}
    chosen = attempt.answers.filter(question=q).values_list("choice_id", flat=True).first()
    return {
        "index": index,
        "total": len(attempt.question_order),
        "question_id": q.pk,
        "text": q.text,
        "points": q.points,
        "choices": [{"id": cid, "text": by_id[cid].text} for cid in attempt.choice_orders[str(q.pk)] if cid in by_id],
        "chosen_choice_id": chosen,
    }


def save_answer(attempt: Attempt, question_id: int, choice_id):
    if question_id not in attempt.question_order:
        raise ExamClosed("سؤال غير صالح.", "bad_question")
    idx = attempt.question_order.index(question_id)
    if not attempt.exam.allow_back and idx != attempt.current_index:
        raise ExamClosed("لا يمكن الرجوع إلى سؤال سابق في هذا الامتحان.", "forward_only")
    if choice_id is not None and not Choice.objects.filter(pk=choice_id, question_id=question_id).exists():
        raise ExamClosed("اختيار غير صالح.", "bad_choice")
    Answer.objects.update_or_create(attempt=attempt, question_id=question_id, defaults={"choice_id": choice_id})
    nxt = max(attempt.current_index, idx + 1)
    if nxt != attempt.current_index:
        attempt.current_index = nxt
        attempt.save(update_fields=["current_index"])


def report_violation(attempt: Attempt, kind: str):
    """Count a browser-reported event; close the attempt when the teacher's limit is reached.
    -> (attempt, counted): `counted` is False for an unknown kind or a repeat of the same "leaving"."""
    if kind not in VIOLATION_TYPES:
        return attempt, False
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update().select_related("exam").get(pk=attempt.pk)
        if attempt.submitted_at:
            return attempt, False
        now = timezone.now()
        log = list(attempt.violation_log)
        family = LEAVE_FAMILY.get(kind, kind)
        if log and LEAVE_FAMILY.get(log[-1]["type"], log[-1]["type"]) == family \
                and (now - datetime.fromisoformat(log[-1]["at"])).total_seconds() < DEDUPE_SECONDS:
            return attempt, False
        log.append({"type": kind, "at": now.isoformat()})
        attempt.violation_log = log[-LOG_CAP:]
        attempt.violations += 1
        attempt.save(update_fields=["violations", "violation_log"])
    if attempt.violations >= attempt.exam.max_violations:
        return finalize(attempt, Attempt.End.VIOLATIONS), True
    return attempt, True
