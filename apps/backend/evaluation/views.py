from rest_framework import generics

from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import Rating, TeacherNote
from .serializers import (
    RatingCreateSerializer,
    RatingSerializer,
    RatingUpdateSerializer,
    TeacherNoteCreateSerializer,
    TeacherNoteSerializer,
    TeacherNoteUpdateSerializer,
)

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]


def _filtered(qs, params):
    if enrollment_id := params.get("enrollment_id"):
        qs = qs.filter(enrollment_id=enrollment_id)
    if session_id := params.get("session_id"):
        qs = qs.filter(session_id=session_id)
    return qs


class TeacherNoteListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = TeacherNote.objects.select_related("enrollment__student", "session")

    def get_queryset(self):
        return _filtered(super().get_queryset(), self.request.query_params)

    def get_serializer_class(self):
        return TeacherNoteCreateSerializer if self.request.method == "POST" else TeacherNoteSerializer


class TeacherNoteDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = TeacherNote.objects.select_related("enrollment__student", "session")

    def get_serializer_class(self):
        return TeacherNoteUpdateSerializer if self.request.method in ("PUT", "PATCH") else TeacherNoteSerializer


class RatingListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = Rating.objects.select_related("enrollment__student", "session")

    def get_queryset(self):
        return _filtered(super().get_queryset(), self.request.query_params)

    def get_serializer_class(self):
        return RatingCreateSerializer if self.request.method == "POST" else RatingSerializer


class RatingDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = Rating.objects.select_related("enrollment__student", "session")

    def get_serializer_class(self):
        return RatingUpdateSerializer if self.request.method in ("PUT", "PATCH") else RatingSerializer
