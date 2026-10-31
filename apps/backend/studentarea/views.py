"""
Student Area API (docs: scope.md "Student Area", functional.md "Student area &
visibility"). A student sees THEIR OWN: attendance, recitation results, payment
STATUS, monthly State, monthly Rating, videos targeted to them, notifications
and quiz results — plus two active features: the AI Quiz and the AI Study
Assistant. Never Teacher Private Notes. Not an LMS.

Isolation rules enforced by construction in this file:
  * every view requires role=student AND an ACTIVE membership of the single
    active environment (IsEnvironmentMember.for_role("student") — server-derived
    context, ADR-008);
  * the student's Enrollment is ALWAYS looked up from (request.environment,
    request.user). No endpoint accepts an enrollment/student id from the client,
    so there is nothing to tamper with;
  * every other query is filtered by that Enrollment (or by request.user +
    request.environment for notifications). No cross-environment merge.
"""
import datetime as dt

from django.db import IntegrityError, transaction
from django.db.models import Count, OuterRef, Q, Subquery
from django.db.models.functions import Length
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment
from accounts.permissions import IsStudent
from accounts.throttles import AISubmitRateThrottle
from ai.models import AIOperation
from ai.quiz_source import QuizSourceError, prepare_quiz_source, teacher_text
from ai.views import AIOperationDetailView, AIOperationListSubmitView
from billing import capabilities
from billing.permissions import RequiresCapability
from config.months import current_month, month_bounds
from content.models import ContentItem, Transcript, VideoProgress

from content.video import describe_video
from environments.tenancy import IsEnvironmentMember
from evaluation.models import MonthlyRating, PrivateNote, StudentState
from financials.models import MonthlyPayment
from notifications.models import Notification
from scheduling.models import AttendanceRecord, RecitationRecord

from .models import Quiz, QuizAttempt

STUDENT = [IsStudent, IsEnvironmentMember.for_role("student")]
MAX_ROWS = 200
MIN_QUIZ_SOURCE_CHARS = 40


def my_enrollment(request) -> Enrollment:
    return generics.get_object_or_404(
        Enrollment.objects.select_related("grade").prefetch_related("groups"),
        environment=request.environment, student=request.user, is_active=True,
    )


class StudentView(APIView):
    permission_classes = STUDENT


def _visible_content(enrollment):
    """Published items targeted at this student (grade AND group narrowing, or
    picked by name). One rule, shared with the teacher-side audience.

    Annotated with the transcript's status and size (never its text, which can
    be ~100k characters per lesson) so list screens can tell whether a quiz is
    possible without N+1 queries or loading transcripts."""
    transcript = Transcript.objects.filter(item=OuterRef("pk"))
    return ContentItem.visible_to(enrollment).annotate(
        transcript_state=Subquery(transcript.values("status")[:1]),
        transcript_chars=Subquery(transcript.annotate(n=Length("text")).values("n")[:1]),
    )


def _can_quiz(item):
    """Mirrors `ai.quiz_source.prepare_quiz_source`: an uploaded video is quizzed
    from its (completed) transcript; anything else from the teacher's text."""
    if item.kind != ContentItem.Kind.VIDEO:
        return False
    if item.source == ContentItem.Source.UPLOAD:
        return (
            getattr(item, "transcript_state", None) == Transcript.Status.COMPLETED
            and (getattr(item, "transcript_chars", None) or 0) + len(teacher_text(item)) >= MIN_QUIZ_SOURCE_CHARS
        )
    if item.kind != ContentItem.Kind.VIDEO:
        return False
    source = f"{item.title}\n{item.description}\n{item.quiz_source}"
    return len(source.strip()) >= MIN_QUIZ_SOURCE_CHARS and bool(item.quiz_source.strip() or len(item.description.strip()) >= 20)


def _video_row(item):
    return {
        "id": item.id, "title": item.title, "description": item.description,
        "video": describe_video(item.video_provider, item.video_ref), "published_at": item.published_at,
        # `source` tells the client whether to stream from Madar (uploaded,
        # ticket-protected) or embed the external player. The stored path is
        # deliberately NOT exposed.
        "source": item.source,
        "kind": item.kind,
        "can_quiz": _can_quiz(item),
    }


def _material_row(item, detail=False):
    """A PDF or a summary as the student sees it. The stored file path is never exposed; a PDF is
    opened through a signed ticket (content.document_views)."""
    row = {"id": item.id, "kind": item.kind, "title": item.title, "description": item.description,
           "published_at": item.published_at}
    if item.kind == ContentItem.Kind.PDF:
        row.update({"original_filename": item.original_filename, "file_size": item.file_size})
    if detail and item.kind == ContentItem.Kind.SUMMARY:
        row["body"] = item.body
    return row


def _month_str(d):
    return d.strftime("%Y-%m")


class OverviewView(StudentView):
    def get(self, request):
        e = my_enrollment(request)
        env = request.environment
        month = current_month()
        start, end = month_bounds(month)
        att = dict(AttendanceRecord.objects.filter(enrollment=e, session__scheduled_at__date__gte=start, session__scheduled_at__date__lt=end)
                   .values_list("status").annotate(n=Count("id")))
        rec = dict(RecitationRecord.objects.filter(enrollment=e, session__scheduled_at__date__gte=start, session__scheduled_at__date__lt=end)
                   .values_list("status").annotate(n=Count("id")))
        pay = MonthlyPayment.objects.filter(enrollment=e, month=month).first()
        state = StudentState.objects.filter(enrollment=e, month=month).first()
        rating = MonthlyRating.objects.filter(enrollment=e, month=month, published_at__isnull=False).first()
        return Response({
            "environment": {"name": env.name},
            # The student's own badge code, so they can show it to the teacher
            # from their phone instead of carrying a printed card. It is the
            # SAME value the teacher scans, so rotating it on the teacher side
            # is reflected here on the next load — no separate copy to drift.
            "student": {"name": e.display_name, "badge_code": e.qr_token},
            "grade": e.grade.name,
            "groups": [g.name for g in e.groups.all()],
            "this_month": {
                "month": _month_str(month),
                "payment": pay.status if pay else "unpaid",
                "state": state.state if state else None,
                "rating": rating.value if rating else None,
                "attendance": {"present": att.get("present", 0), "absent": att.get("absent", 0)},
                "recitation": {"studied": rec.get("studied", 0), "not_studied": rec.get("not_studied", 0)},
            },
            "unread_notifications": Notification.objects.filter(environment=env, recipient=request.user, read_at__isnull=True).count(),
            "latest_videos": [_video_row(v) for v in _visible_content(e).filter(kind=ContentItem.Kind.VIDEO).order_by("-published_at")[:3]],
        })


class _RecordsView(StudentView):
    model = None
    statuses = ()

    def get(self, request):
        e = my_enrollment(request)
        rows = list(self.model.objects.filter(enrollment=e).select_related("session__group").order_by("-session__scheduled_at")[:MAX_ROWS])
        totals = dict(self.model.objects.filter(enrollment=e).values_list("status").annotate(n=Count("id")))
        return Response({
            "summary": {s: totals.get(s, 0) for s in self.statuses},
            "results": [{"id": r.id, "date": r.session.scheduled_at, "group": r.session.group.name, "status": r.status} for r in rows],
        })


class AttendanceView(_RecordsView):
    model, statuses = AttendanceRecord, ("present", "absent")


class RecitationView(_RecordsView):
    model, statuses = RecitationRecord, ("studied", "not_studied")


class PaymentsView(StudentView):
    """Payment STATUS per month (docs: the student sees status, not the fee
    ledger). Months from enrollment to now; an unrecorded month is unpaid —
    the same rule the teacher's sheet uses."""

    def get(self, request):
        e = my_enrollment(request)
        first = e.created_at.date().replace(day=1)
        recorded = {p.month: p for p in MonthlyPayment.objects.filter(enrollment=e)}
        groups = [g.name for g in e.groups.all()]
        rows, cur = [], current_month()
        while cur >= first and len(rows) < 12:
            paid = recorded.get(cur)
            row = {"month": _month_str(cur), "status": paid.status if paid else "unpaid"}
            if paid and paid.status == MonthlyPayment.Status.PAID:
                # A receipt the student keeps: who paid, for what, how much and
                # exactly when — so a disputed month can be settled from the
                # record instead of memory.
                row["receipt"] = {
                    "student_name": e.display_name,
                    "grade": e.grade.name,
                    "groups": groups,
                    "teacher_environment": e.environment.name,
                    "month": _month_str(cur),
                    "amount": str(paid.amount),
                    "paid_at": paid.paid_at,
                    "reference": f"MDR-{e.id}-{cur.strftime('%Y%m')}",
                    "note": paid.note,
                }
            rows.append(row)
            cur = (cur - dt.timedelta(days=1)).replace(day=1)
        return Response({"results": rows})


class EvaluationView(StudentView):
    """Finalized monthly State + PUBLISHED monthly Rating + the teacher's
    written notes for this student.

    Product decision: the notes the teacher writes about a student are shown
    to that student, so the monthly evaluation is explained rather than being
    a bare label. A DRAFT rating is still withheld — that is the teacher's
    work in progress, not a decision yet.

    Scope: only this enrolment's own notes are ever read (`my_enrollment`), so
    nothing here can surface another student's record.
    """

    def get(self, request):
        e = my_enrollment(request)
        by_month = {}
        for s in StudentState.objects.filter(enrollment=e):
            by_month.setdefault(s.month, {})["state"] = s.state
        for r in MonthlyRating.objects.filter(enrollment=e, published_at__isnull=False):
            by_month.setdefault(r.month, {})["rating"] = r.value
        rows = [{"month": _month_str(m), "state": v.get("state"), "rating": v.get("rating")}
                for m, v in sorted(by_month.items(), reverse=True)]
        notes = [{
            "id": n.id,
            "body": n.body,
            "created_at": n.created_at,
            "updated_at": n.updated_at,
        } for n in PrivateNote.objects.filter(enrollment=e).order_by("-created_at")[:MAX_ROWS]]
        return Response({"results": rows, "notes": notes})


class VideoListView(StudentView):
    def get(self, request):
        e = my_enrollment(request)
        items = _visible_content(e).filter(kind=ContentItem.Kind.VIDEO).order_by("-published_at")[:MAX_ROWS]
        return Response({"results": [_video_row(v) for v in items]})


class VideoDetailView(StudentView):
    """One video the student may watch (the page behind the card's «زيارة»).
    Anything not targeted at them is a plain 404 - no existence oracle."""

    def get(self, request, pk):
        e = my_enrollment(request)
        item = generics.get_object_or_404(_visible_content(e).filter(kind=ContentItem.Kind.VIDEO), pk=pk)
        row = _video_row(item)
        prog = VideoProgress.objects.filter(item=item, enrollment=e).first()
        row["progress"] = {"position_seconds": prog.position_seconds, "percent": prog.percent,
                           "completed": prog.completed} if prog else None
        return Response(row)


class MaterialListView(StudentView):
    """PDF files and summaries targeted at this student (`?kind=pdf|summary`, default both)."""

    def get(self, request):
        e = my_enrollment(request)
        kinds = [ContentItem.Kind.PDF, ContentItem.Kind.SUMMARY]
        wanted = request.query_params.get("kind")
        if wanted:
            if wanted not in kinds:
                raise serializers.ValidationError({"kind": "نوع غير صالح."})
            kinds = [wanted]
        items = _visible_content(e).filter(kind__in=kinds).order_by("-published_at")[:MAX_ROWS]
        return Response({"results": [_material_row(i) for i in items]})


class MaterialDetailView(StudentView):
    """One PDF or summary the student may read; anything not targeted at them is a plain 404."""

    def get(self, request, pk):
        e = my_enrollment(request)
        item = generics.get_object_or_404(
            _visible_content(e).filter(kind__in=[ContentItem.Kind.PDF, ContentItem.Kind.SUMMARY]), pk=pk)
        return Response(_material_row(item, detail=True))


class NotificationListView(StudentView):
    def get(self, request):
        qs = Notification.objects.filter(environment=request.environment, recipient=request.user)
        if request.query_params.get("unread") in ("1", "true"):
            qs = qs.filter(read_at__isnull=True)
        qs = qs.select_related("broadcast", "content_item").prefetch_related("broadcast__grades", "broadcast__groups")
        return Response({"results": [
            {"id": n.id, "type": n.type, "type_label": n.get_type_display(), "title": n.title, "body": n.body,
             "created_at": n.created_at, "read": n.read_at is not None,
             # Where "open" should take the student (an exam, a file/summary, a video) — None for the rest.
             "target": n.target(),
             # For a teacher message: who it was addressed to, so the student
             # can open the full context instead of a truncated line.
             "details": ({
                 "title": n.broadcast.title,
                 "body": n.broadcast.body,
                 "grades": [g.name for g in n.broadcast.grades.all()],
                 "groups": [g.name for g in n.broadcast.groups.all()],
                 "sent_at": n.broadcast.created_at,
             } if n.broadcast_id else None)}
            for n in qs.order_by("-created_at", "-id")[:MAX_ROWS]
        ]})


class NotificationReadView(StudentView):
    def post(self, request, pk):
        n = generics.get_object_or_404(Notification.objects.filter(environment=request.environment, recipient=request.user), pk=pk)
        if n.read_at is None:
            n.read_at = timezone.now()
            n.save(update_fields=["read_at"])
        return Response({"id": n.id, "read": True})


class NotificationReadAllView(StudentView):
    def post(self, request):
        n = Notification.objects.filter(environment=request.environment, recipient=request.user, read_at__isnull=True).update(read_at=timezone.now())
        return Response({"marked": n})


# ----------------------------- AI Quiz ---------------------------------------
class QuizRequestSerializer(serializers.Serializer):
    content_id = serializers.IntegerField()
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)

    def validate_idempotency_key(self, value):
        return (value or "").strip() or None


def _op_payload(op):
    quiz = Quiz.objects.filter(operation=op).first()
    return {"id": op.id, "status": op.status, "error": op.error, "quiz_id": quiz.id if quiz else None}


def _quiz_summary(q):
    attempt = getattr(q, "attempt", None) if hasattr(q, "attempt") else None
    return {"id": q.id, "title": q.content_title, "created_at": q.created_at, "questions": len(q.questions),
            "score": attempt.score if attempt else None, "total": attempt.total if attempt else None}


class QuizListRequestView(StudentView):
    """BILL-WU-011: the POST (submit) is gated on `ai.quiz_from_video`; the
    GET (listing already-created quizzes — a read) is not, per this unit's
    own "reads of existing AI results are not gated." `request.environment`
    here is the TEACHER's Environment (resolved the same way, header plus
    active Enrollment, per `my_enrollment`/`IsEnvironmentMember`), never the
    student's — the capability is evaluated against the teacher's plan."""

    def get_permissions(self):
        classes = list(self.permission_classes)
        if self.request.method == "POST":
            classes = classes + [RequiresCapability(capabilities.AI_QUIZ_FROM_VIDEO)]
        return [cls() for cls in classes]

    def get_throttles(self):
        return [AISubmitRateThrottle()] if self.request.method == "POST" else []

    def get(self, request):
        e = my_enrollment(request)
        quizzes = Quiz.objects.filter(enrollment=e).select_related("attempt")[:MAX_ROWS]
        return Response({"results": [_quiz_summary(q) for q in quizzes]})

    def post(self, request):
        """Student-INITIATED (docs): asks for a quiz on a video targeted to
        them. Async submit -> operation id -> poll; idempotent per key (ADR-011)."""
        ser = QuizRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        e = my_enrollment(request)
        item = generics.get_object_or_404(
            _visible_content(e).filter(kind=ContentItem.Kind.VIDEO), pk=ser.validated_data["content_id"])
        key = ser.validated_data.get("idempotency_key")
        env = request.environment
        if key:
            existing = AIOperation.objects.filter(environment=env, requested_by=request.user, idempotency_key=key).first()
            if existing:
                if existing.content_id != item.id:
                    return Response({"detail": "مفتاح التكرار مستخدم مسبقًا مع طلب مختلف.", "code": "idempotency_conflict"}, status=409)
                return Response(_op_payload(existing), status=status.HTTP_200_OK)
        # The COMPLETE lesson material (transcript for uploaded videos, the
        # teacher's text otherwise) - never sliced. If it cannot be prepared the
        # request fails explicitly here, before any operation exists.
        try:
            source = prepare_quiz_source(item)
        except QuizSourceError as exc:
            return Response({"detail": exc.message, "code": exc.code}, status=status.HTTP_409_CONFLICT)
        try:
            with transaction.atomic():
                op = AIOperation.objects.create(
                    environment=env, requested_by=request.user, kind=AIOperation.Kind.QUIZ_GENERATION,
                    enrollment=e, content=item, idempotency_key=key, prompt=f"quiz content#{item.id}",
                    evidence=source.as_evidence(),  # lesson material ONLY (transcript and/or teacher text)
                )
        except IntegrityError:
            op = AIOperation.objects.get(environment=env, requested_by=request.user, idempotency_key=key)
            return Response(_op_payload(op), status=status.HTTP_200_OK)
        return Response(_op_payload(op), status=status.HTTP_202_ACCEPTED)


class QuizOperationView(StudentView):
    def get(self, request, pk):
        op = generics.get_object_or_404(
            AIOperation.objects.filter(environment=request.environment, requested_by=request.user, kind=AIOperation.Kind.QUIZ_GENERATION), pk=pk
        )
        return Response(_op_payload(op))


def _quiz_detail(quiz, attempt=None):
    data = {"id": quiz.id, "title": quiz.content_title, "created_at": quiz.created_at, "submitted": attempt is not None,
            "questions": []}
    for i, q in enumerate(quiz.questions):
        row = {"q": q["q"], "options": q["options"]}
        if attempt is not None:  # correct answers are revealed ONLY after submitting
            row.update({"answer_index": q["answer_index"], "explanation": q.get("explanation", ""),
                        "chosen": attempt.answers[i] if i < len(attempt.answers) else None})
        data["questions"].append(row)
    if attempt is not None:
        data.update({"score": attempt.score, "total": attempt.total, "submitted_at": attempt.submitted_at})
    return data


def _my_quiz(request, pk):
    e = my_enrollment(request)
    return generics.get_object_or_404(Quiz.objects.filter(environment=request.environment, enrollment=e), pk=pk)


class QuizDetailView(StudentView):
    def get(self, request, pk):
        quiz = _my_quiz(request, pk)
        attempt = QuizAttempt.objects.filter(quiz=quiz).first()
        return Response(_quiz_detail(quiz, attempt))


class QuizSubmitSerializer(serializers.Serializer):
    answers = serializers.ListField(child=serializers.IntegerField(allow_null=True), max_length=50)


class QuizSubmitView(StudentView):
    """Auto-scoring happens HERE, server-side, against the persisted quiz."""

    def post(self, request, pk):
        ser = QuizSubmitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        answers = ser.validated_data["answers"]
        with transaction.atomic():
            quiz = generics.get_object_or_404(
                Quiz.objects.select_for_update().filter(environment=request.environment, enrollment=my_enrollment(request)), pk=pk
            )
            if QuizAttempt.objects.filter(quiz=quiz).exists():
                return Response({"detail": "سبق أن أرسلت إجاباتك على هذا الاختبار.", "code": "already_submitted"}, status=409)
            if len(answers) != len(quiz.questions):
                raise serializers.ValidationError({"answers": "عدد الإجابات لا يطابق عدد الأسئلة."})
            for a, q in zip(answers, quiz.questions):
                if a is not None and not 0 <= a < len(q["options"]):
                    raise serializers.ValidationError({"answers": "إجابة غير صالحة."})
            score = sum(1 for a, q in zip(answers, quiz.questions) if a == q["answer_index"])
            attempt = QuizAttempt.objects.create(
                environment_id=quiz.environment_id, quiz=quiz, answers=answers, score=score, total=len(quiz.questions)
            )
        return Response(_quiz_detail(quiz, attempt))


# ------------------------- AI Study Assistant --------------------------------
class AssistantListSubmitView(AIOperationListSubmitView):
    """Same general-tutor pipeline as the teacher's, for the student. The
    operation has no link to any student record (database constraint).

    BILL-WU-011: NOT gated — whether the Study Assistant is plan-gated at
    all is BILL-DEC-07, an open System-level decision this unit does not
    make (its own Escalation conditions). Do not add a RequiresCapability
    check here until BILL-DEC-07 resolves it."""

    permission_classes = STUDENT


class AssistantDetailView(AIOperationDetailView):
    permission_classes = STUDENT
