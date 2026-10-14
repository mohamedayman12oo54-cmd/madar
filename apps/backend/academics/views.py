from django.db import IntegrityError, transaction
from django.db.models import ProtectedError, Q
from rest_framework import generics, serializers, status
from rest_framework.response import Response

from accounts.permissions import IsTeacher
from accounts.phones import digits_only
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
        if instance.member_enrollments.exists():
            raise serializers.ValidationError("لا يمكن حذف مجموعة بها طلاب — انقلهم أولًا.")
        try:
            instance.delete()
        except ProtectedError:  # sessions reference the group (history is never silently erased)
            raise serializers.ValidationError("لا يمكن حذف مجموعة لها جلسات مسجلة.")


class EnrollmentListCreateView(TenantScopedQuerySetMixin, generics.ListAPIView):
    """GET: the teacher's student roster for the active environment (a
    student's presence in an environment is exactly their Enrollment into it).
    POST: enroll a student (existing or new) — see EnrollmentCreateSerializer."""

    permission_classes = IS_ENV_OWNER
    serializer_class = EnrollmentSerializer
    queryset = Enrollment.objects.select_related("student", "grade").prefetch_related("groups")

    def get_throttles(self):
        # Only creating students costs anything; reading the roster must never
        # be locked out by the "add student" budget.
        return [StudentAddRateThrottle()] if self.request.method == "POST" else []

    def get_queryset(self):
        qs = super().get_queryset()
        params = self.request.query_params
        if grade_id := params.get("grade_id"):
            qs = qs.filter(grade_id=grade_id)
        if group_id := params.get("group_id"):
            qs = qs.filter(groups__id=group_id)
        if is_active := params.get("is_active"):
            qs = qs.filter(is_active=is_active.lower() in ("1", "true", "yes"))
        if search := params.get("search", "").replace("\x00", "").strip():
            cond = Q(student_name__icontains=search)
            digits = digits_only(search).lstrip("0")
            if digits:
                cond |= Q(student__phone__contains=digits)
            qs = qs.filter(cond)
        return qs.distinct()

    def post(self, request, *args, **kwargs):
        ser = EnrollmentCreateSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        enrollment, created = ser.save()
        return Response(
            {
                "enrollment_id": enrollment.id,
                "created": created,
                "name": ser.validated_data["name"],
                "phone": ser.validated_data["phone"],
                "grade_id": enrollment.grade_id,
                "group_ids": [g.id for g in ser.validated_data["groups"]] if created else [],
                "academic_year": enrollment.academic_year,
            },
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class EnrollmentDetailView(TenantScopedQuerySetMixin, generics.RetrieveUpdateAPIView):
    """No DELETE: an enrollment is a historical relationship, not a row to
    drop — "removing" a student is `PATCH {"is_active": false}`."""

    permission_classes = IS_ENV_OWNER
    queryset = Enrollment.objects.select_related("student", "grade").prefetch_related("groups")

    def get_serializer_class(self):
        return EnrollmentUpdateSerializer if self.request.method in ("PUT", "PATCH") else EnrollmentSerializer

    def update(self, request, *args, **kwargs):
        kwargs["partial"] = True  # PUT behaves like PATCH: every field is optional
        super().update(request, *args, **kwargs)
        return Response(EnrollmentSerializer(self.get_object()).data)
