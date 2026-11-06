"""
The teacher's side of the guardian portal: send a warning / note about ONE child to that child's guardian.

Strictly environment-scoped like every teacher endpoint: the enrollment must belong to the caller's own
environment, whatever id the body names.
"""
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment
from accounts.permissions import IsTeacher
from accounts.throttles import GuardianMessageRateThrottle
from environments.tenancy import IsEnvironmentMember

from .auth import guardian_visible_q
from .models import GuardianAlertSettings, GuardianMessage, GuardianReply

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
HISTORY_LIMIT = 50


class GuardianMessageSerializer(serializers.Serializer):
    enrollment_id = serializers.IntegerField()
    kind = serializers.ChoiceField(choices=GuardianMessage.Kind.choices, default=GuardianMessage.Kind.NOTE)
    title = serializers.CharField(max_length=150)
    body = serializers.CharField(max_length=1000)


def _row(m, replies=()):
    return {"id": m.id, "kind": m.kind, "kind_label": m.get_kind_display(),
            "title": m.title, "body": m.body, "created_at": m.created_at, "automatic": m.automatic,
            "read_at": m.read_at,
            "replies": [{"id": r.id, "body": r.body, "created_at": r.created_at, "read_at": r.read_at}
                        for r in replies]}


def _env_enrollment(request, pk):
    return get_object_or_404(Enrollment.objects.filter(environment=request.environment), pk=pk)


class GuardianMessageView(APIView):
    permission_classes = IS_ENV_OWNER
    throttle_classes = [GuardianMessageRateThrottle]

    def get(self, request):
        """What this teacher already sent to one child's guardian (newest first)."""
        try:
            pk = int(request.query_params.get("enrollment", ""))
        except ValueError:
            raise serializers.ValidationError({"enrollment": "حدد الطالب."})
        enrollment = _env_enrollment(request, pk)
        rows = (GuardianMessage.objects.filter(environment=request.environment, enrollment=enrollment)
                .prefetch_related("replies")[:HISTORY_LIMIT])
        return Response({"results": [_row(m, m.replies.all()) for m in rows]})

    def post(self, request):
        ser = GuardianMessageSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        enrollment = _env_enrollment(request, v["enrollment_id"])
        if not enrollment.parent_phone:
            raise serializers.ValidationError(
                {"detail": "لا يوجد رقم ولي أمر مسجّل لهذا الطالب. أضفه من تعديل بيانات الطالب أولًا.",
                 "code": "no_guardian_phone"})
        message = GuardianMessage.objects.create(
            environment=request.environment, enrollment=enrollment, kind=v["kind"],
            title=v["title"].strip(), body=v["body"].strip(), sent_by=request.user)
        # Whether the guardian can open the portal right now: the child must have activated their account.
        can_view = (enrollment.is_active
                    and Enrollment.objects.filter(pk=enrollment.pk).filter(guardian_visible_q()).exists())
        return Response({**_row(message), "guardian_can_view": can_view}, status=status.HTTP_201_CREATED)


class UnreadRepliesView(APIView):
    """How many guardian replies this teacher has not opened yet, per student: the badge on the students list."""

    permission_classes = IS_ENV_OWNER

    def get(self, request):
        rows = (GuardianReply.objects.filter(environment=request.environment, read_at__isnull=True)
                .values("enrollment_id").annotate(n=Count("id")))
        return Response({"counts": {str(r["enrollment_id"]): r["n"] for r in rows}})


class ReadRepliesView(APIView):
    """The teacher opened one student conversation: its replies count as read."""

    permission_classes = IS_ENV_OWNER

    def post(self, request):
        try:
            pk = int(request.data.get("enrollment_id"))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"enrollment_id": "حدد الطالب."})
        enrollment = _env_enrollment(request, pk)
        n = GuardianReply.objects.filter(
            environment=request.environment, enrollment=enrollment, read_at__isnull=True,
        ).update(read_at=timezone.now())
        return Response({"marked": n})


class AlertSettingsSerializer(serializers.Serializer):
    enabled = serializers.BooleanField()
    absence_threshold = serializers.IntegerField(min_value=0, max_value=31)
    exam_percent_below = serializers.IntegerField(min_value=0, max_value=100)
    unpaid_after_day = serializers.IntegerField(min_value=0, max_value=28)
    show_rank = serializers.BooleanField(required=False)


def _settings_row(cfg):
    return {"enabled": cfg.enabled, "absence_threshold": cfg.absence_threshold,
            "exam_percent_below": cfg.exam_percent_below, "unpaid_after_day": cfg.unpaid_after_day,
            "show_rank": cfg.show_rank}


class GuardianAlertSettingsView(APIView):
    """Whether the system warns guardians by itself, and at what limits. Off until the teacher turns it on."""

    permission_classes = IS_ENV_OWNER

    def get(self, request):
        cfg, _ = GuardianAlertSettings.objects.get_or_create(environment=request.environment)
        return Response(_settings_row(cfg))

    def put(self, request):
        ser = AlertSettingsSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        cfg, _ = GuardianAlertSettings.objects.update_or_create(
            environment=request.environment, defaults=ser.validated_data)
        return Response(_settings_row(cfg))
