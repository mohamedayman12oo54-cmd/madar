from django.db import transaction
from django.utils import timezone
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin
from notifications.models import Notification
from notifications.services import notify_many

from .models import ContentItem
from .serializers import ContentItemSerializer, ContentItemWriteSerializer

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
_PREFETCH = ("target_grades", "target_groups", "target_enrollments")


class ContentListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = ContentItem.objects.prefetch_related(*_PREFETCH)

    def get_queryset(self):
        qs = super().get_queryset()
        p = self.request.query_params
        if grade_id := p.get("grade_id"):
            qs = qs.filter(target_grades__id=grade_id)
        if search := p.get("search", "").strip():
            qs = qs.filter(title__icontains=search)
        if p.get("published") in ("1", "true"):
            qs = qs.filter(published_at__isnull=False)
        elif p.get("published") in ("0", "false"):
            qs = qs.filter(published_at__isnull=True)
        return qs.distinct()

    def get_serializer_class(self):
        return ContentItemWriteSerializer if self.request.method == "POST" else ContentItemSerializer


class ContentDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = ContentItem.objects.prefetch_related(*_PREFETCH)

    def get_serializer_class(self):
        return ContentItemWriteSerializer if self.request.method in ("PUT", "PATCH") else ContentItemSerializer


class ContentPublishView(APIView):
    """Make the item watchable by its targets AND fire "new video available"
    once. Requires a target and (for a video item) a video reference; a second
    publish is a 409, never a duplicate notification."""

    permission_classes = IS_ENV_OWNER

    def post(self, request, pk):
        with transaction.atomic():
            item = generics.get_object_or_404(
                ContentItem.objects.select_for_update().filter(environment=request.environment), pk=pk
            )
            if item.published_at:
                return Response({"detail": "تم نشر هذا المحتوى من قبل.", "code": "already_published"}, status=409)
            if not item.has_targets():
                raise serializers.ValidationError({"detail": "حدّد صفًا أو مجموعة أو طلابًا قبل النشر."})
            item.published_at = timezone.now()
            item.save(update_fields=["published_at"])
            recipients = notify_many(
                list(item.audience()), Notification.Type.NEW_VIDEO, "فيديو جديد", f"تمت إضافة: {item.title}"[:500],
                content_item=item,
            )
        item = ContentItem.objects.prefetch_related(*_PREFETCH).get(pk=item.pk)
        return Response({**ContentItemSerializer(item).data, "notified": len(recipients)})
