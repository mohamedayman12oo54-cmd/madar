"""Student side of exams. Same isolation rule as the rest of the student area: the enrollment is
always looked up from (request.environment, request.user); no endpoint takes a student id.

What a student can never receive from here: which choice is correct (until the teacher's release
rules allow the review, and never before the window closes), another student's paper or score."""
from django.db.models import Count, Sum
from rest_framework import generics, serializers
from rest_framework.response import Response

from accounts.throttles import ExamAnswerRateThrottle, ExamEventRateThrottle
from studentarea.views import StudentView, my_enrollment

from . import services
from .models import Attempt, Exam, IntegrityEvent


def _guard(fn):
    """Turn a service refusal into the stable {"detail", "code"} error body."""
    def run(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except services.ExamError as e:
            return Response({"detail": e.detail, "code": e.code}, status=e.status)
    return run


def _my_exam(request, pk):
    e = my_enrollment(request)
    exam = generics.get_object_or_404(
        Exam.visible_to(e).annotate(n_questions=Count("questions", distinct=True),
                                    total=Sum("questions__points")), pk=pk)
    return e, exam


def _row(exam, attempt, at):
    state = services.window_state(exam, at)
    if attempt is None:
        status = {"upcoming": "upcoming", "open": "open", "closed": "missed"}[state]
    elif attempt.submitted:
        status = "submitted"
    else:
        status = "in_progress"
    row = {
        "id": exam.id, "title": exam.title, "description": exam.description,
        "duration_minutes": exam.duration_minutes, "question_count": getattr(exam, "n_questions", None),
        "total_points": getattr(exam, "total", None) or 0,
        "opens_at": exam.effective_opens_at(), "closes_at": exam.closes_at, "status": status,
        "score": None, "max_score": None, "results_pending": False,
    }
    if attempt is not None and attempt.submitted:
        if services.results_released(exam, attempt, at):
            row["score"], row["max_score"] = attempt.score, attempt.max_score
        else:
            row["results_pending"] = True
    return row


class ExamListView(StudentView):
    def get(self, request):
        e = my_enrollment(request)
        at = services.now()
        exams = list(Exam.visible_to(e).annotate(n_questions=Count("questions", distinct=True),
                                                 total=Sum("questions__points"))[:200])
        attempts = {a.exam_id: a for a in Attempt.objects.filter(enrollment=e, exam__in=exams)}
        for a in attempts.values():
            if not a.submitted:
                attempts[a.exam_id] = services.finalize_if_due(a.pk)
        return Response({"results": [_row(x, attempts.get(x.id), at) for x in exams]})


class ExamDetailView(StudentView):
    """Everything BEFORE the paper: title, duration, window, status. No questions."""

    def get(self, request, pk):
        e, exam = _my_exam(request, pk)
        a = Attempt.objects.filter(exam=exam, enrollment=e).first()
        if a and not a.submitted:
            a = services.finalize_if_due(a.pk)
        return Response({**_row(exam, a, services.now()), "max_violations": exam.max_violations})


def _paper(exam, attempt):
    """The student's own copy of the paper, in their own order, WITHOUT the answer key."""
    questions = {q.id: q for q in exam.questions.prefetch_related("choices")}
    saved = {a.question_id: a.choice_id for a in attempt.answers.all()}
    out = []
    for qid in attempt.question_order:
        q = questions.get(qid)
        if q is None:
            continue
        by_id = {c.id: c for c in q.choices.all()}
        order = attempt.choice_order.get(str(qid)) or list(by_id)
        out.append({
            "id": q.id, "text": q.text, "points": q.points,
            "choices": [{"id": cid, "text": by_id[cid].text} for cid in order if cid in by_id],
            "chosen": saved.get(q.id),
        })
    return out


def _attempt_payload(exam, attempt):
    return {
        "attempt": {
            "id": attempt.id, "started_at": attempt.started_at, "deadline_at": attempt.deadline_at,
            "violations": attempt.violations, "max_violations": exam.max_violations,
            "submitted": attempt.submitted, "submit_reason": attempt.submit_reason,
        },
        # the server's clock, so the page can show a countdown that does not trust the device clock
        "server_now": services.now(),
        "title": exam.title,
        "questions": [] if attempt.submitted else _paper(exam, attempt),
    }


class ExamStartView(StudentView):
    """Start the exam, or come back to the one in progress (same paper, same deadline)."""

    @_guard
    def post(self, request, pk):
        e, exam = _my_exam(request, pk)
        attempt, created = services.start_attempt(exam, e)
        return Response(_attempt_payload(exam, attempt), status=201 if created else 200)


class AnswerSerializer(serializers.Serializer):
    question_id = serializers.IntegerField()
    choice_id = serializers.IntegerField(allow_null=True)


class ExamAnswerView(StudentView):
    throttle_classes = [ExamAnswerRateThrottle]

    @_guard
    def put(self, request, pk):
        e, exam = _my_exam(request, pk)
        ser = AnswerSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attempt = generics.get_object_or_404(Attempt, exam=exam, enrollment=e)
        services.save_answer(attempt.pk, ser.validated_data["question_id"], ser.validated_data["choice_id"])
        return Response({"saved": True})


class EventSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=IntegrityEvent.Kind.choices)


class ExamEventView(StudentView):
    throttle_classes = [ExamEventRateThrottle]

    @_guard
    def post(self, request, pk):
        e, exam = _my_exam(request, pk)
        ser = EventSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attempt = generics.get_object_or_404(Attempt, exam=exam, enrollment=e)
        attempt, counted = services.record_event(attempt.pk, ser.validated_data["kind"])
        return Response({"violations": attempt.violations, "max_violations": exam.max_violations,
                         "counted": counted, "submitted": attempt.submitted,
                         "submit_reason": attempt.submit_reason})


class ExamSubmitView(StudentView):
    """Idempotent: submitting twice (a double tap, a retry after a dropped reply) returns the same state."""

    @_guard
    def post(self, request, pk):
        e, exam = _my_exam(request, pk)
        attempt = generics.get_object_or_404(Attempt, exam=exam, enrollment=e)
        attempt = services.submit(attempt.pk)
        return Response(_result(exam, attempt))


def _result(exam, attempt):
    at = services.now()
    out = {"submitted": attempt.submitted, "submit_reason": attempt.submit_reason,
           "violations": attempt.violations, "results_pending": False, "score": None, "max_score": None}
    if attempt.submitted:
        if services.results_released(exam, attempt, at):
            out["score"], out["max_score"] = attempt.score, attempt.max_score
        else:
            out["results_pending"] = True
    return out


class ExamResultView(StudentView):
    @_guard
    def get(self, request, pk):
        e, exam = _my_exam(request, pk)
        attempt = generics.get_object_or_404(Attempt, exam=exam, enrollment=e)
        attempt = services.finalize_if_due(attempt.pk)
        if not attempt.submitted:
            raise services.ExamError("لم تُسلّم هذا الامتحان بعد.", "not_submitted", 409)
        out = _result(exam, attempt)
        at = services.now()
        if services.review_allowed(exam, attempt, at):
            answers = {a.question_id: a.choice_id for a in attempt.answers.all()}
            review = []
            for q in exam.questions.prefetch_related("choices"):
                correct = next((c for c in q.choices.all() if c.is_correct), None)
                review.append({
                    "id": q.id, "text": q.text, "points": q.points,
                    "choices": [{"id": c.id, "text": c.text} for c in q.choices.all()],
                    "correct_choice_id": correct.id if correct else None,
                    "chosen_choice_id": answers.get(q.id),
                })
            out["review"] = review
        return Response(out)
