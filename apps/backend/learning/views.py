"""Teacher side of exams: build, publish, and read results."""
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment
from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember
from notifications.models import Notification
from notifications.services import notify_enrollment, notify_many

from . import services
from .models import Attempt, AttemptGrant, Exam
from .serializers import ExamWriteSerializer, exam_read

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
_PREFETCH = ("target_grades", "target_groups", "target_enrollments")


def _exams(request):
    return Exam.objects.filter(environment=request.environment).prefetch_related(*_PREFETCH)


class ExamListCreateView(APIView):
    permission_classes = IS_ENV_OWNER

    def get(self, request):
        rows = [exam_read(e, with_answers=False) for e in _exams(request)]
        return Response({"results": rows})

    def post(self, request):
        ser = ExamWriteSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            exam = ser.save()
        return Response(exam_read(exam), status=status.HTTP_201_CREATED)


class ExamDetailView(APIView):
    permission_classes = IS_ENV_OWNER

    def get(self, request, pk):
        return Response(exam_read(get_object_or_404(_exams(request), pk=pk)))

    def put(self, request, pk):
        exam = get_object_or_404(_exams(request), pk=pk)
        # Once anyone has started, the questions are frozen: editing them would change what some
        # students were already graded against.
        if exam.attempts.exists():
            raise serializers.ValidationError(
                {"detail": "بدأ بعض الطلاب هذا الامتحان، لا يمكن تعديله. أنشئ امتحانًا جديدًا."})
        ser = ExamWriteSerializer(exam, data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        with transaction.atomic():
            exam = ser.save()
        return Response(exam_read(exam))

    def delete(self, request, pk):
        get_object_or_404(_exams(request), pk=pk).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ExamPublishView(APIView):
    permission_classes = IS_ENV_OWNER

    def post(self, request, pk):
        with transaction.atomic():
            exam = get_object_or_404(Exam.objects.select_for_update().filter(environment=request.environment), pk=pk)
            if exam.published_at:
                return Response({"detail": "تم نشر هذا الامتحان من قبل.", "code": "already_published"}, status=409)
            if not exam.questions.exists():
                raise serializers.ValidationError({"detail": "أضف أسئلة قبل النشر."})
            if not exam.has_targets():
                raise serializers.ValidationError({"detail": "حدّد صفًا أو مجموعة أو طلابًا قبل النشر."})
            exam.published_at = timezone.now()
            exam.save(update_fields=["published_at"])
            sent = notify_many(list(exam.audience()), Notification.Type.NEW_EXAM, "امتحان جديد",
                               f"تم نشر امتحان: {exam.title}"[:500], exam=exam)
        return Response({**exam_read(get_object_or_404(_exams(request), pk=pk), with_answers=False),
                         "notified": len(sent)})


class ExamResultsView(APIView):
    """Every student in the audience: not started / in progress / finished, with the BEST score (the one that
    counts), every sitting, and whether the exam can be re-opened for that student."""

    permission_classes = IS_ENV_OWNER

    def get(self, request, pk):
        exam = get_object_or_404(_exams(request), pk=pk)
        attempts = {}
        for a in exam.attempts.select_related("enrollment__student").order_by("number"):
            attempts.setdefault(a.enrollment_id, []).append(a)
        for sittings in attempts.values():
            sittings[-1] = services.expire_if_due(sittings[-1])
        reopened = set(exam.grants.filter(used_by__isnull=True).values_list("enrollment_id", flat=True))
        is_open = services.availability(exam) == "open"
        rows = [_row(e, attempts.pop(e.pk, []), e.pk in reopened, is_open)
                for e in exam.audience().select_related("student")]
        for sittings in attempts.values():  # students no longer in the audience but who did sit it
            rows.append(_row(sittings[0].enrollment, sittings, sittings[0].enrollment_id in reopened, is_open))
        counted = [r for r in rows if r["status"] != "not_started" and r.get("percent") is not None]
        finished = [r for r in rows if r["status"] == "finished"]
        avg = round(sum(r["percent"] for r in counted) / len(counted), 1) if counted else None
        return Response({"exam_id": exam.pk, "title": exam.title, "average_percent": avg,
                         "finished": len(finished), "total": len(rows), "results": rows})


class ExamReopenView(APIView):
    """Teacher: "something went wrong for this student" — let him sit the exam once more. His earlier sitting
    stays on record and the BEST score is the one that counts. Notifies the student."""

    permission_classes = IS_ENV_OWNER

    def post(self, request, pk):
        exam = get_object_or_404(_exams(request), pk=pk)
        if exam.published_at is None:
            raise serializers.ValidationError({"detail": "انشر الامتحان أولًا."})
        eid = request.data.get("enrollment_id") if isinstance(request.data, dict) else None
        if not isinstance(eid, int):
            raise serializers.ValidationError({"enrollment_id": "حدّد الطالب."})
        enrollment = exam.audience().filter(pk=eid).first() or \
            Enrollment.objects.filter(environment=request.environment, pk=eid, exam_attempts__exam=exam).first()
        if enrollment is None:
            raise serializers.ValidationError({"enrollment_id": "هذا الطالب ليس ضمن مستلمي الامتحان."})
        with transaction.atomic():
            fresh = not exam.grants.filter(enrollment=enrollment, used_by__isnull=True).exists()
            try:
                services.reopen(exam, enrollment, by=request.user)
            except services.ExamClosed as e:
                raise serializers.ValidationError({"detail": e.message, "code": e.code})
            if fresh:
                notify_enrollment(enrollment, Notification.Type.NEW_EXAM, "أُعيد فتح الامتحان لك",
                                  f"أتاح لك معلمك محاولة أخرى في: {exam.title}"[:500], exam=exam)
        return Response({"enrollment_id": enrollment.pk, "reopened": True, "already": not fresh})


def _attempt_row(a):
    base = {"number": a.number, "status": "finished" if a.submitted_at else "in_progress",
            "violations": a.violations, "violation_log": a.violation_log, "started_at": a.started_at}
    if not a.submitted_at:
        return base
    return {**base, "score": a.score, "max_score": a.max_score, "percent": services.percent(a),
            "end_reason": a.end_reason, "submitted_at": a.submitted_at}


def _row(enrollment, sittings, reopened, exam_is_open):
    base = {"enrollment_id": enrollment.pk, "name": enrollment.display_name,
            "phone": getattr(enrollment.student, "phone", None),
            "attempt_count": len(sittings), "reopened": reopened,
            "attempts": [_attempt_row(a) for a in sittings]}
    if not sittings:
        return {**base, "status": "not_started", "can_reopen": not reopened and not exam_is_open}
    best = services.best_attempt(sittings)
    running = not sittings[-1].submitted_at
    status = "in_progress" if running else "finished"
    row = {**base, "status": status, "can_reopen": not running and not reopened}
    if best:  # the score that counts: the best finished sitting
        row.update(score=best.score, max_score=best.max_score, percent=services.percent(best),
                   end_reason=best.end_reason, violations=best.violations, violation_log=best.violation_log,
                   submitted_at=best.submitted_at, best_attempt=best.number)
    else:
        row["violations"] = sittings[-1].violations
    return row
