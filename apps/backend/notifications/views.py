from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import Notification
from .serializers import NotificationSerializer

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]


class NotificationListView(TenantScopedQuerySetMixin, generics.ListAPIView):
    """A teacher only ever sees THEIR OWN notifications — tenant-scoped by
    environment (Phase 1 mechanism) AND by recipient, since a Notification
    row belongs to one specific recipient, not to "the environment" at
    large the way Grade/Group/Enrollment do."""

    permission_classes = IS_ENV_OWNER
    serializer_class = NotificationSerializer
    queryset = Notification.objects.all()

    def get_queryset(self):
        qs = super().get_queryset().filter(recipient=self.request.user)
        if unread := self.request.query_params.get("unread"):
            if unread.lower() in ("1", "true", "yes"):
                qs = qs.filter(read_at__isnull=True)
        return qs


class NotificationMarkReadView(APIView):
    permission_classes = IS_ENV_OWNER

    def post(self, request, pk):
        notification = generics.get_object_or_404(
            Notification.objects.filter(environment=request.environment, recipient=request.user), pk=pk
        )
        if notification.read_at is None:
            notification.read_at = timezone.now()
            notification.save(update_fields=["read_at"])
        return Response(NotificationSerializer(notification).data)


class UnreadCountView(APIView):
    permission_classes = IS_ENV_OWNER

    def get(self, request):
        count = Notification.objects.filter(
            environment=request.environment, recipient=request.user, read_at__isnull=True
        ).count()
        return Response({"unread_count": count})
