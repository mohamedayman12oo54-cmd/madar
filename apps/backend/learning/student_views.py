"""Student side of exams. The student is ALWAYS derived from the token + environment, never from a body."""
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsStudent
from accounts.throttles import ExamAnswerRateThrottle, ExamEventRateThrottle
from environments.tenancy import IsEnvironmentMember
from studentarea.views import my_enrollment

from . import services
from .models import Attempt, AttemptGrant, Exam

STUDENT = [IsStudent, IsEnvironmentMember.for_role("student")]
NO_STORE = {"Cache-Control": "no-store, private", "X-Content-Type-Options": "nosniff"}


def _json(data, status=200):
    return Response(data, status=status, headers=NO_STORE)


def _fail(e: services.ExamClosed):
    raise serializers.ValidationError({"detail": e.message, "code": e.code})


def _attempt_state(a: Attempt):
    return {"attempt_id": a.pk, "number": a.number, "deadline_at": a.deadline_at, "started_at": a.started_at,
            "total": len(a.question_order), "current_index": a.current_index,
            "violations": a.violations, "max_violations": a.exam.max_violations,
            "warnings_left": max(0, a.exam.max_violations - a.violations),
            "allow_back": a.exam.allow_back, "title": a.exam.title,
            "finished": a.finished, "end_reason": a.end_reason}


class _Base(APIView):
    permission_classes = STUDENT

    def exam_for(self, request, pk):
        enrollment = my_enrollment(request)
        exam = get_object_or_404(Exam.visible_to(enrollment).prefetch_related("questions"), pk=pk)
        return enrollment, exam

    def attempt_for(self, enrollment, exam):
        """The student's CURRENT sitting = the newest attempt (a re-opened exam adds attempts 2, 3 …)."""
        a = services.latest_attempt(exam, enrollment)
        return services.expire_if_due(a) if a else None


class ExamListView(_Base):
    def get(self, request):
        enrollment = my_enrollment(request)
        mine = {}
        for a in Attempt.objects.select_related("exam").filter(enrollment=enrollment).order_by("exam_id", "number"):
            mine.setdefault(a.exam_id, []).append(a)
        for rows_ in mine.values():  # the newest sitting may have run out of time since the student left
            rows_[-1] = services.expire_if_due(rows_[-1])
        reopened = set(AttemptGrant.objects.filter(enrollment=enrollment, used_by__isnull=True)
                       .values_list("exam_id", flat=True))
        rows = []
        for e in Exam.visible_to(enrollment):
            atts = mine.get(e.pk, [])
            latest = atts[-1] if atts else None
            best = services.best_attempt(atts)
            can_retake = bool(best and latest.finished and e.pk in reopened)
            if latest and not latest.finished:
                state = "in_progress"
            elif best:
                state = "finished"
            elif e.pk in reopened:
                state = "open"
            else:
                state = services.availability(e)
            row = {"id": e.pk, "title": e.title, "description": e.description,
                   "duration_minutes": e.duration_minutes, "question_count": e.questions.count(),
                   "opens_at": e.opens_at, "closes_at": e.closes_at, "state": state,
                   "max_violations": e.max_violations, "allow_back": e.allow_back,
                   "attempts": len(atts), "can_retake": can_retake, "reopened": e.pk in reopened}
            if best:  # the score that COUNTS is the best one
                row.update(score=best.score, max_score=best.max_score, percent=services.percent(best))
            rows.append(row)
        return _json({"results": rows})


class ExamStartView(_Base):
    def post(self, request, pk):
        enrollment, exam = self.exam_for(request, pk)
        data = request.data if isinstance(request.data, dict) else {}
        try:
            a = services.start_or_resume(exam, enrollment, retake=data.get("retake") is True)
        except services.ExamClosed as e:
            _fail(e)
        return _json(_attempt_state(a))


class ExamQuestionView(_Base):
    def get(self, request, pk, index):
        enrollment, exam = self.exam_for(request, pk)
        a = self.attempt_for(enrollment, exam)
        if a is None:
            raise serializers.ValidationError({"detail": "ابدأ الامتحان أولًا.", "code": "not_started"})
        if a.finished:
            raise serializers.ValidationError({"detail": "انتهى الامتحان.", "code": "finished"})
        if index >= len(a.question_order):
            raise serializers.ValidationError({"detail": "لا يوجد هذا السؤال.", "code": "bad_question"})
        # Forward-only: only the CURRENT question can be read. Otherwise, up to the furthest reached.
        if (not exam.allow_back and index != a.current_index) or index > a.current_index:
            raise serializers.ValidationError({"detail": "لا يمكن الوصول لهذا السؤال الآن.", "code": "forward_only"})
        return _json({**services.question_payload(a, index), **_attempt_state(a)})


class ExamAnswerView(_Base):
    throttle_classes = [ExamAnswerRateThrottle]

    def post(self, request, pk):
        enrollment, exam = self.exam_for(request, pk)
        a = self.attempt_for(enrollment, exam)
        if a is None or a.finished:
            raise serializers.ValidationError({"detail": "انتهى الامتحان أو لم يبدأ.", "code": "finished"})
        data = request.data if isinstance(request.data, dict) else {}
        qid, cid = data.get("question_id"), data.get("choice_id")
        if not isinstance(qid, int) or not (cid is None or isinstance(cid, int)):
            raise serializers.ValidationError({"detail": "بيانات غير صالحة."})
        try:
            services.save_answer(a, qid, cid)
        except services.ExamClosed as e:
            _fail(e)
        a.refresh_from_db()
        return _json(_attempt_state(a))


class ExamViolationView(_Base):
    throttle_classes = [ExamEventRateThrottle]

    def post(self, request, pk):
        enrollment, exam = self.exam_for(request, pk)
        a = self.attempt_for(enrollment, exam)
        if a is None:
            return _json({"ignored": True})
        kind = request.data.get("type") if isinstance(request.data, dict) else None
        a, counted = services.report_violation(a, kind if isinstance(kind, str) else "")
        # `counted` tells the page whether to show a NEW warning (a repeat of one "leaving" is not counted again).
        return _json({**_attempt_state(a), "counted": counted, "last_violation": kind if counted else None})


class ExamSubmitView(_Base):
    def post(self, request, pk):
        enrollment, exam = self.exam_for(request, pk)
        a = self.attempt_for(enrollment, exam)
        if a is None:
            raise serializers.ValidationError({"detail": "لم تبدأ هذا الامتحان.", "code": "not_started"})
        a = services.finalize(a, Attempt.End.SUBMITTED)
        return _json(_attempt_state(a))


class ExamResultView(_Base):
    """Score only, unless the teacher chose to reveal the answers — and then only after the attempt is over
    and only when the student has no further sitting waiting (otherwise the key would leak into the retake).
    `score` / `percent` describe the sitting just finished; `best_*` is the one that counts."""

    def get(self, request, pk):
        enrollment, exam = self.exam_for(request, pk)
        a = self.attempt_for(enrollment, exam)
        if a is None or not a.finished:
            raise serializers.ValidationError({"detail": "النتيجة غير متاحة بعد.", "code": "not_finished"})
        mine = list(Attempt.objects.filter(exam=exam, enrollment=enrollment))
        best = services.best_attempt(mine)
        can_retake = AttemptGrant.objects.filter(exam=exam, enrollment=enrollment, used_by__isnull=True).exists()
        out = {"title": exam.title, "attempt_number": a.number, "score": a.score, "max_score": a.max_score,
               "percent": services.percent(a), "end_reason": a.end_reason, "violations": a.violations,
               "attempts": len([x for x in mine if x.finished]), "can_retake": can_retake,
               "best_score": best.score, "best_percent": services.percent(best), "is_best": best.pk == a.pk}
        if exam.reveal_answers and not can_retake:
            given = {x.question_id: x.choice_id for x in a.answers.all()}
            out["review"] = [
                {"text": q.text, "choices": [{"text": c.text, "is_correct": c.is_correct,
                                              "chosen": given.get(q.pk) == c.pk} for c in q.choices.all()]}
                for q in exam.questions.prefetch_related("choices")
            ]
        return _json(out)
