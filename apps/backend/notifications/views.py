from django.db import transaction
from django.db.models import Count, Q
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment, Grade, Group
from accounts.permissions import IsTeacher
from accounts.throttles import BroadcastRateThrottle
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import Broadcast, Notification
from .serializers import BroadcastSerializer, NotificationSerializer
from .services import notify_many

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
MAX_BROADCAST_RECIPIENTS = 2000


def _supports_distinct_on():
    """PostgreSQL has DISTINCT ON; SQLite does not."""
    from django.db import connection

    return connection.features.can_distinct_on_fields


class NotificationListView(TenantScopedQuerySetMixin, generics.ListAPIView):
    """The teacher's log of notifications fired in THIS environment. The
    environment filter is the isolation boundary — a teacher can never see
    another teacher's notifications."""

    permission_classes = IS_ENV_OWNER
    serializer_class = NotificationSerializer
    queryset = Notification.objects.select_related("enrollment", "broadcast", "content_item", "exam").prefetch_related(
        "broadcast__grades", "broadcast__groups", "content_item__target_grades", "content_item__target_groups",
        "exam__target_grades", "exam__target_groups")

    @staticmethod
    def _first_ids(qs, field):
        """Newest delivery id for each distinct `field` (broadcast / content_item / exam)."""
        col = f"{field}_id"
        if _supports_distinct_on():
            return list(qs.filter(**{f"{field}__isnull": False}).order_by(col, "-created_at", "-id")
                        .distinct(col).values_list("id", flat=True))
        seen, keep = set(), []
        for key, nid in qs.filter(**{f"{field}__isnull": False}).order_by("-created_at", "-id").values_list(col, "id"):
            if key not in seen:
                seen.add(key)
                keep.append(nid)
        return keep

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if t := p.get("type"):
            qs = qs.filter(type=t)
        if s := p.get("delivery_status"):
            qs = qs.filter(delivery_status=s)
        # A broadcast is ONE message that happened to be delivered to many
        # students. Showing every delivery turns a message to 40 students into
        # 40 log rows and buries the per-student events (absence, recitation)
        # that actually need attention. Keep a single representative row per
        # broadcast; the full audience lives behind its details view.
        if p.get("collapse", "1") not in ("0", "false"):
            # One representative row per broadcast AND per published video / file / summary / exam.
            keep_q = Q(broadcast__isnull=True, content_item__isnull=True, exam__isnull=True)
            for field in ("broadcast", "content_item", "exam"):
                keep_q |= Q(id__in=self._first_ids(qs, field))
            qs = qs.filter(keep_q)
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
        # Targeting is a NARROWING, not a union. Picking a grade AND a group
        # must reach the students in that group — previously the `|` meant it
        # also hit everyone else in the grade, so a message aimed at one group
        # went to the whole year.
        qs = Enrollment.objects.filter(environment=env, is_active=True)
        if grade_ids:
            qs = qs.filter(grade_id__in=grade_ids)
        if group_ids:
            qs = qs.filter(groups__id__in=group_ids)
        enrollments = list(qs.distinct()[: MAX_BROADCAST_RECIPIENTS + 1])
        if not enrollments:
            raise serializers.ValidationError({"detail": "لا يوجد طلاب نشطون في هذه الاختيارات."})
        if len(enrollments) > MAX_BROADCAST_RECIPIENTS:
            raise serializers.ValidationError({"detail": "عدد المستلمين أكبر من الحد المسموح في رسالة واحدة."})
        with transaction.atomic():
            message = Broadcast.objects.create(
                environment=env, title=v["title"], body=v["body"],
                recipient_count=len(enrollments), sent_by=request.user)
            message.grades.set(grade_ids)
            message.groups.set(group_ids)
            notify_many(enrollments, Notification.Type.BROADCAST, v["title"], v["body"],
                        broadcast=message)
        return Response({"id": message.id, "recipients": len(enrollments)},
                        status=status.HTTP_201_CREATED)


class RetryFailedView(APIView):
    """Put this environment's FAILED deliveries back in the queue."""

    permission_classes = IS_ENV_OWNER

    def post(self, request):
        n = Notification.objects.filter(
            environment=request.environment, delivery_status=Notification.DeliveryStatus.FAILED
        ).update(delivery_status=Notification.DeliveryStatus.PENDING, delivery_error="")
        return Response({"requeued": n})


class BroadcastLogView(generics.ListAPIView):
    """The teacher's sent messages: ONE row per message, not one per student."""

    permission_classes = IS_ENV_OWNER
    pagination_class = None

    def get(self, request):
        rows = (Broadcast.objects.filter(environment=request.environment)
                .prefetch_related("grades", "groups")[:100])
        return Response({"results": [{
            "id": b.id,
            "title": b.title,
            "body": b.body,
            "recipient_count": b.recipient_count,
            "grades": [g.name for g in b.grades.all()],
            "groups": [g.name for g in b.groups.all()],
            "created_at": b.created_at,
        } for b in rows]})


class BroadcastDetailView(APIView):
    """Full message + exactly who received it."""

    permission_classes = IS_ENV_OWNER

    def get(self, request, pk):
        b = generics.get_object_or_404(
            Broadcast.objects.filter(environment=request.environment), pk=pk)
        deliveries = (b.deliveries.select_related("enrollment")
                      .order_by("enrollment__student_name")[:MAX_BROADCAST_RECIPIENTS])
        return Response({
            "id": b.id, "title": b.title, "body": b.body,
            "recipient_count": b.recipient_count,
            "grades": [g.name for g in b.grades.all()],
            "groups": [g.name for g in b.groups.all()],
            "created_at": b.created_at,
            "recipients": [{
                "enrollment_id": d.enrollment_id,
                "name": d.enrollment.display_name if d.enrollment else "",
                "delivery_status": d.delivery_status,
            } for d in deliveries],
        })
