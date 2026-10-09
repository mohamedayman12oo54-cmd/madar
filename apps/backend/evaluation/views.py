from django.db import IntegrityError, transaction
from django.db.models import Count, Q
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment
from accounts.permissions import IsTeacher
from config.months import current_month, month_bounds, parse_month
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin
from notifications.models import Notification
from notifications.services import notify_enrollment
from scheduling.models import AttendanceRecord, RecitationRecord

from .models import MonthlyRating, PrivateNote, StudentState
from .serializers import (
    NoteCreateSerializer,
    NoteSerializer,
    RatingPublishAllSerializer,
    RatingPublishSerializer,
    RatingUpsertSerializer,
    StateUpsertSerializer,
)

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
MAX_ROWS = 1000


def month_evidence(env, month, enrollment_ids):
    """Attendance / recitation counts for the month, per enrollment. Only
    aggregates — this same shape is what the advisory AI recommendation is
    given (no names, no notes)."""
    start, end = month_bounds(month)
    out = {i: {"present": 0, "absent": 0, "studied": 0, "not_studied": 0} for i in enrollment_ids}
    for model, key_map in ((AttendanceRecord, ("present", "absent")), (RecitationRecord, ("studied", "not_studied"))):
        rows = (
            model.objects.filter(environment=env, enrollment_id__in=enrollment_ids,
                                 session__scheduled_at__date__gte=start, session__scheduled_at__date__lt=end)
            .values("enrollment_id", "status").annotate(n=Count("id"))
        )
        for r in rows:
            if r["status"] in key_map:
                out[r["enrollment_id"]][r["status"]] = r["n"]
    return out


def _enrollment(request, enrollment_id):
    return generics.get_object_or_404(Enrollment.objects.filter(environment=request.environment), pk=enrollment_id)


class MonthlyEvaluationView(APIView):
    """The month's evaluation sheet for ACTIVE students of the caller's
    environment: rating (draft/published), finalized state, the month's
    evidence, and the latest advisory AI recommendation (if any)."""

    permission_classes = IS_ENV_OWNER

    def get(self, request):
        from ai.models import AIOperation

        p = request.query_params
        month = parse_month(p.get("month") or current_month().strftime("%Y-%m"))
        env = request.environment
        qs = Enrollment.objects.filter(environment=env, is_active=True).select_related("grade")
        if gid := p.get("grade_id"):
            qs = qs.filter(grade_id=gid)
        if grp := p.get("group_id"):
            qs = qs.filter(groups__id=grp)
        if search := p.get("search", "").strip():
            qs = qs.filter(student_name__icontains=search)
        enrollments = list(qs.distinct().order_by("student_name", "id")[:MAX_ROWS])
        ids = [e.id for e in enrollments]
        ratings = {r.enrollment_id: r for r in MonthlyRating.objects.filter(environment=env, month=month, enrollment_id__in=ids)}
        states = {s.enrollment_id: s for s in StudentState.objects.filter(environment=env, month=month, enrollment_id__in=ids)}
        recs = {}
        for op in AIOperation.objects.filter(
            environment=env, kind="state_recommendation", month=month, enrollment_id__in=ids
        ).order_by("created_at"):
            recs[op.enrollment_id] = op  # latest wins
        evidence = month_evidence(env, month, ids)
        rows = []
        for e in enrollments:
            r, s, op = ratings.get(e.id), states.get(e.id), recs.get(e.id)
            rows.append({
                "enrollment_id": e.id, "name": e.display_name, "grade": e.grade.name,
                "rating": {"value": r.value, "published": bool(r.published_at)} if r else None,
                "state": s.state if s else None,
                "evidence": evidence[e.id],
                "recommendation": {
                    "operation_id": op.id, "status": op.status, "suggested_state": op.suggested_state, "rationale": op.result,
                } if op else None,
            })
        return Response({"month": month.strftime("%Y-%m"), "rows": rows})


def _upsert(model, enrollment, month, env, **fields):
    for _ in range(2):
        try:
            with transaction.atomic():
                obj, created = model.objects.select_for_update().get_or_create(
                    enrollment=enrollment, month=month, defaults={"environment": env, **fields}
                )
                if not created:
                    for k, v in fields.items():
                        setattr(obj, k, v)
                    obj.save()
                return obj
        except IntegrityError:
            continue
    raise serializers.ValidationError({"detail": "تعذّر الحفظ، حاول مرة أخرى."})


class RatingUpsertView(APIView):
    permission_classes = IS_ENV_OWNER

    def put(self, request):
        ser = RatingUpsertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        enrollment = _enrollment(request, v["enrollment_id"])
        if not enrollment.is_active:
            raise serializers.ValidationError({"detail": "الطالب غير نشط."})
        obj = _upsert(MonthlyRating, enrollment, v["month"], request.environment, value=v["value"])
        return Response({"enrollment_id": enrollment.id, "month": v["month"].strftime("%Y-%m"),
                         "value": obj.value, "published": bool(obj.published_at)})


def _publish(rating, enrollment):
    rating.published_at = timezone.now()
    rating.save(update_fields=["published_at", "updated_at"])
    notify_enrollment(
        enrollment, Notification.Type.RATING_PUBLISHED, "تم نشر تقييمك الشهري",
        f"تم نشر تقييمك لشهر {rating.month:%Y-%m}.",
    )


class RatingPublishView(APIView):
    """Publishing is a one-time event: it fires ONE notification. Publishing an
    already-published rating is a 409, never a duplicate notification."""

    permission_classes = IS_ENV_OWNER

    def post(self, request):
        ser = RatingPublishSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        enrollment = _enrollment(request, v["enrollment_id"])
        with transaction.atomic():
            rating = MonthlyRating.objects.select_for_update().filter(
                environment=request.environment, enrollment=enrollment, month=v["month"]
            ).first()
            if not rating:
                raise serializers.ValidationError({"detail": "لا يوجد تقييم لهذا الشهر لنشره."})
            if rating.published_at:
                return Response({"detail": "تم نشر هذا التقييم من قبل.", "code": "already_published"}, status=409)
            _publish(rating, enrollment)
        return Response({"enrollment_id": enrollment.id, "published": True})


class RatingPublishAllView(APIView):
    permission_classes = IS_ENV_OWNER

    def post(self, request):
        ser = RatingPublishAllSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        env = request.environment
        qs = MonthlyRating.objects.filter(environment=env, month=v["month"], published_at__isnull=True,
                                          enrollment__is_active=True).select_related("enrollment")
        if gid := v.get("grade_id"):
            qs = qs.filter(enrollment__grade_id=gid)
        if grp := v.get("group_id"):
            qs = qs.filter(enrollment__groups__id=grp)
        published = 0
        with transaction.atomic():
            for rating in qs.select_for_update(of=("self",)).distinct():
                _publish(rating, rating.enrollment)
                published += 1
        return Response({"published": published})


class StateUpsertView(APIView):
    """The TEACHER finalizes the state — the stored value is always theirs."""

    permission_classes = IS_ENV_OWNER

    def put(self, request):
        ser = StateUpsertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        enrollment = _enrollment(request, v["enrollment_id"])
        if not enrollment.is_active:
            raise serializers.ValidationError({"detail": "الطالب غير نشط."})
        obj = _upsert(StudentState, enrollment, v["month"], request.environment, state=v["state"], finalized_by=request.user)
        return Response({"enrollment_id": enrollment.id, "month": v["month"].strftime("%Y-%m"), "state": obj.state})


class NoteListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    """Teacher-private. There is no student-facing route to this model at all."""

    permission_classes = IS_ENV_OWNER
    queryset = PrivateNote.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        if eid := self.request.query_params.get("enrollment_id"):
            qs = qs.filter(enrollment_id=eid)
        return qs

    def get_serializer_class(self):
        return NoteCreateSerializer if self.request.method == "POST" else NoteSerializer

    def perform_create(self, serializer):
        enrollment = _enrollment(self.request, serializer.validated_data.pop("enrollment_id"))
        serializer.save(environment=self.request.environment, enrollment=enrollment, author=self.request.user)


class NoteDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = PrivateNote.objects.all()
    serializer_class = NoteSerializer
