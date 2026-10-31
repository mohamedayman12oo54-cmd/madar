"""Exam rules that must hold no matter which endpoint calls them: the clock, the single attempt,
grading and the integrity counter. Views stay thin; tests drive these through the API."""
import random
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.utils import timezone

from .models import Attempt, AttemptAnswer, Choice, Exam, IntegrityEvent, Question

_rng = random.SystemRandom()


def now():
    """The one place the clock is read, so tests can move time."""
    return timezone.now()


class ExamError(Exception):
    """A rule refused the request. `code` is stable for the client, `status` is the HTTP status."""

    def __init__(self, detail, code, status=409):
        super().__init__(detail)
        self.detail, self.code, self.status = detail, code, status


# --- the window ----------------------------------------------------------------------------------
def window_state(exam, at):
    """draft | upcoming | open | closed - from the exam alone, regardless of any student."""
    if not exam.published_at:
        return "draft"
    opens = exam.effective_opens_at()
    if at < opens:
        return "upcoming"
    if at >= exam.closes_at:
        return "closed"
    return "open"


def results_released(exam, attempt, at):
    """May this student see their score now?"""
    if not attempt.submitted:
        return False
    if exam.results_release == Exam.Release.IMMEDIATE:
        return True
    return at >= exam.closes_at


def review_allowed(exam, attempt, at):
    """The correct choices are shown only once the whole window is over (see Exam.reveal_answers)."""
    return exam.reveal_answers and results_released(exam, attempt, at) and at >= exam.closes_at


# --- starting ------------------------------------------------------------------------------------
def start_attempt(exam, enrollment):
    """Create the student's attempt, or return the one in progress. A submitted attempt is final."""
    at = now()
    state = window_state(exam, at)
    existing = Attempt.objects.filter(exam=exam, enrollment=enrollment).first()
    if existing:
        return finalize_if_due(existing.pk), False
    if state == "upcoming":
        raise ExamError("لم يبدأ موعد هذا الامتحان بعد.", "exam_not_open", 403)
    if state != "open":
        raise ExamError("انتهى موعد هذا الامتحان.", "exam_closed", 403)

    questions = list(exam.questions.prefetch_related("choices"))
    if not questions:
        raise ExamError("هذا الامتحان لا يحتوي على أسئلة.", "exam_empty", 409)
    order = [q.id for q in questions]
    if exam.shuffle_questions:
        _rng.shuffle(order)
    choice_order = {}
    for q in questions:
        ids = [c.id for c in q.choices.all()]
        if exam.shuffle_choices:
            _rng.shuffle(ids)
        choice_order[str(q.id)] = ids
    deadline = min(at + timedelta(minutes=exam.duration_minutes), exam.closes_at)
    try:
        with transaction.atomic():
            attempt = Attempt.objects.create(
                exam=exam, enrollment=enrollment, started_at=at, deadline_at=deadline,
                question_order=order, choice_order=choice_order)
    except IntegrityError:  # two taps on "start" raced: the other one won, use it
        return finalize_if_due(Attempt.objects.get(exam=exam, enrollment=enrollment).pk), False
    return attempt, True


# --- finishing -----------------------------------------------------------------------------------
def grade(attempt):
    """Sum of the points of the questions answered with the correct choice. Server-side only."""
    exam_questions = {q.id: q.points for q in attempt.exam.questions.all()}
    correct = set(Choice.objects.filter(question__exam=attempt.exam, is_correct=True).values_list("id", flat=True))
    got = 0
    for a in attempt.answers.all():
        if a.choice_id in correct and a.question_id in exam_questions:
            got += exam_questions[a.question_id]
    return got, sum(exam_questions.values())


def _submit_locked(attempt, reason, at):
    if attempt.submitted:
        return attempt
    attempt.score, attempt.max_score = grade(attempt)
    attempt.submitted_at = min(at, attempt.deadline_at) if reason == Attempt.Reason.TIME else at
    attempt.submit_reason = reason
    attempt.save(update_fields=["score", "max_score", "submitted_at", "submit_reason"])
    return attempt


def submit(attempt_id, reason=Attempt.Reason.MANUAL):
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update().select_related("exam").get(pk=attempt_id)
        return _submit_locked(attempt, reason, now())


def finalize_if_due(attempt_id):
    """If the student's time is up and they never submitted, grade what was saved. Called on every
    read/write, so an abandoned tab cannot keep an attempt open forever."""
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update().select_related("exam").get(pk=attempt_id)
        if not attempt.submitted and now() >= attempt.deadline_at:
            _submit_locked(attempt, Attempt.Reason.TIME, now())
        return attempt


def finalize_overdue(exam):
    """Teacher-side: settle every attempt of this exam whose time is up (nobody has to be online)."""
    due = exam.attempts.filter(submitted_at__isnull=True, deadline_at__lte=now()).values_list("pk", flat=True)
    for pk in list(due):
        finalize_if_due(pk)


# --- answers -------------------------------------------------------------------------------------
def save_answer(attempt_id, question_id, choice_id):
    # Settle a lapsed attempt in its OWN transaction first: raising inside the transaction that grades
    # it would roll the grading back and leave the attempt open.
    if finalize_if_due(attempt_id).submitted:
        raise ExamError("انتهى وقت الامتحان أو تم تسليمه.", "attempt_finished", 409)
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update().select_related("exam").get(pk=attempt_id)
        if attempt.submitted:
            raise ExamError("انتهى وقت الامتحان أو تم تسليمه.", "attempt_finished", 409)
        question = Question.objects.filter(exam_id=attempt.exam_id, pk=question_id).first()
        if not question:
            raise ExamError("السؤال غير موجود في هذا الامتحان.", "bad_question", 400)
        if choice_id is None:
            AttemptAnswer.objects.filter(attempt=attempt, question=question).delete()
            return attempt
        choice = Choice.objects.filter(question=question, pk=choice_id).first()
        if not choice:
            raise ExamError("الاختيار لا يخص هذا السؤال.", "bad_choice", 400)
        AttemptAnswer.objects.update_or_create(attempt=attempt, question=question, defaults={"choice": choice})
        return attempt


# --- integrity -----------------------------------------------------------------------------------
def record_event(attempt_id, kind):
    """Log one signal from the exam page. Returns (attempt, counted). Reaching the teacher's limit
    submits the attempt on the spot."""
    if kind not in IntegrityEvent.Kind.values:
        raise ExamError("نوع غير معروف.", "bad_event", 400)
    with transaction.atomic():
        attempt = Attempt.objects.select_for_update().select_related("exam").get(pk=attempt_id)
        at = now()
        if not attempt.submitted and at >= attempt.deadline_at:
            _submit_locked(attempt, Attempt.Reason.TIME, at)
        if attempt.submitted:
            return attempt, False
        if attempt.events.count() >= IntegrityEvent.MAX_PER_ATTEMPT:
            return attempt, False
        counted = kind in IntegrityEvent.COUNTED
        if counted:
            last = attempt.events.filter(counted=True).order_by("-at").first()
            # blur + hidden + fullscreen-exit from ONE departure are one violation, not three
            if last and at - last.at < IntegrityEvent.COUNT_DEBOUNCE:
                counted = False
        IntegrityEvent.objects.create(attempt=attempt, kind=kind, counted=counted, at=at)
        if counted:
            attempt.violations += 1
            attempt.save(update_fields=["violations"])
            if attempt.violations >= attempt.exam.max_violations:
                _submit_locked(attempt, Attempt.Reason.VIOLATIONS, at)
        return attempt, counted
