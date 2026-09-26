from django.db import IntegrityError, transaction
from django.db.models import Q
from rest_framework import generics, serializers, status
from rest_framework.response import Response

from accounts.permissions import IsTeacher
from accounts.throttles import StudentAddRateThrottle
from environments.tenancy import IsEnvironmentMember, TenantScopedQuerySetMixin

from .models import Enrollment, Grade, Group
from .serializers import (
    EnrollmentCreateSerializer,
    EnrollmentSerializer,
    EnrollmentUpdateSerializer,
    GradeSerializer,
    GroupRenameSerializer,
    GroupSerializer,
    GroupWriteSerializer,
)

# Grade/Group/Enrollment management is teacher-owner-only for now (no
# Content-Maintainer/team write access is specified for this phase).
IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]


class GradeListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    permission_classes = IS_ENV_OWNER
    serializer_class = GradeSerializer
    queryset = Grade.objects.all()

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                super().perform_create(serializer)
        except IntegrityError:
            raise serializers.ValidationError({"name": "يوجد صف بنفس الاسم في هذه البيئة بالفعل."})


class GradeDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_ENV_OWNER
    serializer_class = GradeSerializer
    queryset = Grade.objects.all()

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise serializers.ValidationError({"name": "يوجد صف بنفس الاسم في هذه البيئة بالفعل."})

    def perform_destroy(self, instance):
        if instance.enrollments.exists() or instance.groups.exists():
            raise serializers.ValidationError("لا يمكن حذف صف مرتبط بمجموعات أو تسجيلات قائمة.")
        instance.delete()


class GroupListCreateView(TenantScopedQuerySetMixin, generics.ListCreateAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = Group.objects.select_related("grade")

    def get_queryset(self):
        qs = super().get_queryset()
        grade_id = self.request.query_params.get("grade_id")
        return qs.filter(grade_id=grade_id) if grade_id else qs

    def get_serializer_class(self):
        return GroupWriteSerializer if self.request.method == "POST" else GroupSerializer

    def perform_create(self, serializer):
        try:
            with transaction.atomic():
                super().perform_create(serializer)
        except IntegrityError:
            raise serializers.ValidationError({"name": "يوجد مجموعة بنفس الاسم في هذا الصف بالفعل."})


class GroupDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_ENV_OWNER
    queryset = Group.objects.select_related("grade")

    def get_serializer_class(self):
        return GroupRenameSerializer if self.request.method in ("PUT", "PATCH") else GroupSerializer

    def perform_update(self, serializer):
        try:
            with transaction.atomic():
                serializer.save()
        except IntegrityError:
            raise serializers.ValidationError({"name": "يوجد مجموعة بنفس الاسم في هذا الصف بالفعل."})

    def perform_destroy(self, instance):
        if instance.enrollments.exists():
            raise serializers.ValidationError("لا يمكن حذف مجموعة بها طلاب — انقلهم أولًا.")
        instance.delete()


class EnrollmentListCreateView(TenantScopedQuerySetMixin, generics.ListAPIView):
    """GET: the teacher's student roster for the active environment (this IS
    the "Students" list the dashboard's Students section reads — a student's
    presence in an environment is exactly their Enrollment into it).
    POST: enroll a student (existing or new) — see EnrollmentCreateSerializer."""

    permission_classes = IS_ENV_OWNER
    serializer_class = EnrollmentSerializer
    queryset = Enrollment.objects.select_related("student", "grade", "group")
    throttle_classes = [StudentAddRateThrottle]  # only meaningfully limits POST; harmless on GET

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if grade_id := params.get("grade_id"):
            qs = qs.filter(grade_id=grade_id)
        if group_id := params.get("group_id"):
            qs = qs.filter(group_id=group_id)
        if is_active := params.get("is_active"):
            qs = qs.filter(is_active=is_active.lower() in ("1", "true", "yes"))
        if search := params.get("search", "").strip():
            qs = qs.filter(Q(student__name__icontains=search) | Q(student__phone__icontains=search))
        return qs

    def post(self, request, *args, **kwargs):
        ser = EnrollmentCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        enrollment, created = ser.save()
        return Response(
            {
                "enrollment_id": enrollment.id,
                "name": ser.validated_data["name"],
                "phone": ser.validated_data["phone"],
                "grade_id": enrollment.grade_id,
                "group_id": enrollment.group_id,
                "academic_year": enrollment.academic_year,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class EnrollmentDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateAPIView):
    """No DELETE: an enrollment is a historical relationship, not a row to
    drop — "removing" a student is `PATCH {"is_active": false}`."""

    permission_classes = IS_ENV_OWNER
    queryset = Enrollment.objects.select_related("student", "grade", "group")

    def get_serializer_class(self):
        return EnrollmentUpdateSerializer if self.request.method in ("PUT", "PATCH") else EnrollmentSerializer

    def update(self, request, *args, **kwargs):
        super().update(request, *args, **kwargs)
        # Respond with the full read shape (including nested student/grade),
        # not the bare {"group": ..., "is_active": ...} the write serializer
        # would otherwise produce.
        return Response(EnrollmentSerializer(self.get_object()).data)
