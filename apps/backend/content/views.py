from rest_framework import generics

from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import ContentItem
from .serializers import ContentItemSerializer, ContentItemWriteSerializer

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]


class ContentListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = ContentItem.objects.select_related("grade")

    def get_queryset(self):
        qs = super().get_queryset()
        if grade_id := self.request.query_params.get("grade_id"):
            qs = qs.filter(grade_id=grade_id)
        if search := self.request.query_params.get("search", "").strip():
            qs = qs.filter(title__icontains=search)
        return qs

    def get_serializer_class(self):
        return ContentItemWriteSerializer if self.request.method == "POST" else ContentItemSerializer


class ContentDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = ContentItem.objects.select_related("grade")

    def get_serializer_class(self):
        return ContentItemWriteSerializer if self.request.method in ("PUT", "PATCH") else ContentItemSerializer
