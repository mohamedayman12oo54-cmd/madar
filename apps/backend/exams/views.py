"""Teacher side of exams: write the paper, send it, read the results and the integrity log."""
from django.db import transaction
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin
from notifications.models import Notification
from notifications.services import notify_many

from . import services
from .models import Attempt, Exam
from .serializers import ExamSerializer, ExamWriteSerializer

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
_PREFETCH = ("target_grades", "target_groups", "target_enrollments", "questions__choices", "attempts")


class ExamListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = Exam.objects.prefetch_related(*_PREFETCH)

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if p.get("published") in ("1", "true"):
            qs = qs.filter(published_at__isnull=False)
        elif p.get("published") in ("0", "false"):
            qs = qs.filter(published_at__isnull=True)
        if search := p.get("search", "").replace("\x00", "").strip():
            qs = qs.filter(title__icontains=search)
        return qs

    def get_serializer_class(self):
        return ExamWriteSerializer if self.request.method == "POST" else ExamSerializer

    def get_serializer_context(self):
        return {**super().get_serializer_context(), "list": self.request.method == "GET"}


class ExamDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = Exam.objects.prefetch_related(*_PREFETCH)

    def get_serializer_class(self):
        return ExamWriteSerializer if self.request.method in ("PUT", "PATCH") else ExamSerializer

    def destroy(self, request, *args, **kwargs):
        exam = self.get_object()
        if exam.attempts.exists():
            return Response({"detail": "بدأ طلاب هذا الامتحان فلا يمكن حذفه حفاظًا على نتائجهم.",
                             "code": "has_attempts"}, status=409)
        return super().destroy(request, *args, **kwargs)


class ExamPublishView(APIView):
    """Send the exam to its targets and tell them once. A second publish is a 409."""

    permission_classes = IS_ENV_OWNER

    def post(self, request, pk):
        with transaction.atomic():
            exam = generics.get_object_or_404(
                Exam.objects.select_for_update().filter(environment=request.environment), pk=pk)
            if exam.published_at:
                return Response({"detail": "تم إرسال هذا الامتحان من قبل.", "code": "already_published"}, status=409)
            if not exam.has_targets():
                raise serializers.ValidationError({"detail": "حدّد صفًا أو مجموعة أو طلابًا قبل الإرسال."})
            questions = list(exam.questions.prefetch_related("choices"))
            if not questions:
                raise serializers.ValidationError({"detail": "أضف سؤالًا واحدًا على الأقل قبل الإرسال."})
            for q in questions:
                if sum(1 for c in q.choices.all() if c.is_correct) != 1:
                    raise serializers.ValidationError({"detail": "لكل سؤال إجابة صحيحة واحدة قبل الإرسال."})
            if exam.closes_at <= services.now():
                raise serializers.ValidationError({"closes_at": "موعد الإغلاق انقضى. عدّله قبل الإرسال."})
            exam.published_at = services.now()
            exam.save(update_fields=["published_at"])
            # The notification catalog is fixed (new_video); only the wording says it is an exam.
            recipients = notify_many(list(exam.audience()), Notification.Type.NEW_VIDEO, "امتحان جديد",
                                     f"تم إرسال امتحان: {exam.title}"[:500])
        exam = Exam.objects.prefetch_related(*_PREFETCH).get(pk=exam.pk)
        return Response({**ExamSerializer(exam).data, "notified": len(recipients)})


def _owned_exam(request, pk):
    return generics.get_object_or_404(Exam.objects.filter(environment=request.environment), pk=pk)


class ExamResultsView(APIView):
    """Every student who should sit the exam, with their status, score and violation count."""

    permission_classes = IS_ENV_OWNER

    def get(self, request, pk):
        exam = _owned_exam(request, pk)
        if not exam.published_at:
            return Response({"detail": "لم يُرسل هذا الامتحان بعد.", "code": "not_published"}, status=409)
        services.finalize_overdue(exam)
        attempts = {a.enrollment_id: a for a in exam.attempts.all()}
        rows, scored = [], []
        for e in exam.audience().select_related("student").prefetch_related("groups").order_by("id"):
            a = attempts.get(e.id)
            row = {
                "enrollment_id": e.id, "name": e.display_name,
                "groups": [g.name for g in e.groups.all()],
                "attempt_id": a.id if a else None,
                "status": "not_started" if not a else ("submitted" if a.submitted else "in_progress"),
                "score": a.score if a else None, "max_score": a.max_score if a else None,
                "violations": a.violations if a else 0,
                "submit_reason": a.submit_reason if a else "",
                "started_at": a.started_at if a else None, "submitted_at": a.submitted_at if a else None,
            }
            if a and a.submitted and a.max_score:
                scored.append(a.score)
            rows.append(row)
        # students who sat the exam and were later removed from the audience still keep their result
        listed = {r["enrollment_id"] for r in rows}
        for eid, a in attempts.items():
            if eid not in listed:
                rows.append({
                    "enrollment_id": eid, "name": a.enrollment.display_name, "groups": [],
                    "attempt_id": a.id, "status": "submitted" if a.submitted else "in_progress",
                    "score": a.score, "max_score": a.max_score, "violations": a.violations,
                    "submit_reason": a.submit_reason, "started_at": a.started_at, "submitted_at": a.submitted_at,
                })
                if a.submitted and a.max_score:
                    scored.append(a.score)
        total = sum(q.points for q in exam.questions.all())
        return Response({
            "exam": {"id": exam.id, "title": exam.title, "total_points": total, "closes_at": exam.closes_at},
            "summary": {
                "audience": len(rows),
                "started": sum(1 for r in rows if r["status"] != "not_started"),
                "submitted": sum(1 for r in rows if r["status"] == "submitted"),
                "flagged": sum(1 for r in rows if r["violations"] > 0),
                "average": round(sum(scored) / len(scored), 2) if scored else None,
                "highest": max(scored) if scored else None, "lowest": min(scored) if scored else None,
            },
            "results": rows,
        })


class ExamAttemptView(APIView):
    """One student's attempt in full (answers + integrity log), and the teacher's reset."""

    permission_classes = IS_ENV_OWNER

    def _attempt(self, request, pk, attempt_id):
        exam = _owned_exam(request, pk)
        return exam, generics.get_object_or_404(
            Attempt.objects.select_related("enrollment__student").filter(exam=exam), pk=attempt_id)

    def get(self, request, pk, attempt_id):
        exam, attempt = self._attempt(request, pk, attempt_id)
        attempt = services.finalize_if_due(attempt.pk)
        answers = {a.question_id: a.choice_id for a in attempt.answers.all()}
        questions = []
        for q in exam.questions.prefetch_related("choices"):
            correct = next((c for c in q.choices.all() if c.is_correct), None)
            picked = answers.get(q.id)
            questions.append({
                "id": q.id, "text": q.text, "points": q.points,
                "choices": [{"id": c.id, "text": c.text} for c in q.choices.all()],
                "correct_choice_id": correct.id if correct else None, "chosen_choice_id": picked,
                "is_correct": bool(correct and picked == correct.id),
            })
        return Response({
            "attempt": {
                "id": attempt.id, "name": attempt.enrollment.display_name, "status":
                "submitted" if attempt.submitted else "in_progress", "score": attempt.score,
                "max_score": attempt.max_score, "violations": attempt.violations,
                "submit_reason": attempt.submit_reason, "started_at": attempt.started_at,
                "submitted_at": attempt.submitted_at,
            },
            "events": [{"kind": e.kind, "label": e.get_kind_display(), "counted": e.counted, "at": e.at}
                       for e in attempt.events.all()],
            "questions": questions,
        })

    def delete(self, request, pk, attempt_id):
        """Give this student a fresh attempt (a dropped connection, a false alarm). Their answers and
        integrity log for the discarded attempt are removed with it."""
        exam, attempt = self._attempt(request, pk, attempt_id)
        attempt.delete()
        return Response(status=204)
