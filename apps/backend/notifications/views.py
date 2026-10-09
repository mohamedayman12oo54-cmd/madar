from django.db import transaction
from django.db.models import Count, Q
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment, Grade, Group
from accounts.permissions import IsTeacher
from accounts.throttles import BroadcastRateThrottle
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import Notification
from .serializers import BroadcastSerializer, NotificationSerializer
from .services import notify_many

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
MAX_BROADCAST_RECIPIENTS = 2000


class NotificationListView(TenantScopedQuerySetMixin, generics.ListAPIView):
    """The teacher's log of notifications fired in THIS environment. The
    environment filter is the isolation boundary — a teacher can never see
    another teacher's notifications."""

    permission_classes = IS_ENV_OWNER
    serializer_class = NotificationSerializer
    queryset = Notification.objects.select_related("enrollment")

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if t := p.get("type"):
            qs = qs.filter(type=t)
        if s := p.get("delivery_status"):
            qs = qs.filter(delivery_status=s)
        return qs


class NotificationSummaryView(APIView):
    permission_classes = IS_ENV_OWNER

    def get(self, request):
        rows = Notification.objects.filter(environment=request.environment).values("delivery_status").annotate(n=Count("id"))
        counts = {r["delivery_status"]: r["n"] for r in rows}
        return Response({"pending": counts.get("pending", 0), "sent": counts.get("sent", 0), "failed": counts.get("failed", 0)})


class BroadcastView(APIView):
    """Teacher manual broadcast to Groups/Grades (the 5th documented event).
    Targets are validated against the caller's OWN environment; recipients are
    the ACTIVE enrollments of those targets, de-duplicated."""

    permission_classes = IS_ENV_OWNER
    throttle_classes = [BroadcastRateThrottle]

    def post(self, request):
        ser = BroadcastSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        env = request.environment
        grade_ids, group_ids = list(dict.fromkeys(v["grade_ids"])), list(dict.fromkeys(v["group_ids"]))
        if Grade.objects.filter(environment=env, id__in=grade_ids).count() != len(grade_ids):
            raise serializers.ValidationError({"grade_ids": "صف غير موجود."})
        if Group.objects.filter(environment=env, id__in=group_ids).count() != len(group_ids):
            raise serializers.ValidationError({"group_ids": "مجموعة غير موجودة."})
        enrollments = list(
            Enrollment.objects.filter(environment=env, is_active=True)
            .filter(Q(grade_id__in=grade_ids) | Q(groups__id__in=group_ids)).distinct()[: MAX_BROADCAST_RECIPIENTS + 1]
        )
        if not enrollments:
            raise serializers.ValidationError({"detail": "لا يوجد طلاب نشطون في هذه الاختيارات."})
        if len(enrollments) > MAX_BROADCAST_RECIPIENTS:
            raise serializers.ValidationError({"detail": "عدد المستلمين أكبر من الحد المسموح في رسالة واحدة."})
        with transaction.atomic():
            notify_many(enrollments, Notification.Type.BROADCAST, v["title"], v["body"])
        return Response({"recipients": len(enrollments)}, status=status.HTTP_201_CREATED)


class RetryFailedView(APIView):
    """Put this environment's FAILED deliveries back in the queue."""

    permission_classes = IS_ENV_OWNER

    def post(self, request):
        n = Notification.objects.filter(
            environment=request.environment, delivery_status=Notification.DeliveryStatus.FAILED
        ).update(delivery_status=Notification.DeliveryStatus.PENDING, delivery_error="")
        return Response({"requeued": n})
