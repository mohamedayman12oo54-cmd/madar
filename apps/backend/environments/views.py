from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsStudent, IsTeacher
from accounts.throttles import StudentAddRateThrottle

from .models import Environment, EnvironmentMembership
from .serializers import AddStudentSerializer, StudentEnvironmentSerializer, TeacherEnvironmentSerializer


class TeacherEnvironmentListView(APIView):
    permission_classes = [IsTeacher]

    def get(self, request):
        envs = Environment.objects.filter(owner=request.user)
        data = TeacherEnvironmentSerializer(envs, many=True, context={"request": request}).data
        return Response(data)


class TeacherEnvironmentEnterView(APIView):
    permission_classes = [IsTeacher]

    def post(self, request, pk):
        membership = EnvironmentMembership.objects.filter(
            environment_id=pk, environment__owner=request.user, user=request.user
        ).first()
        if not membership:
            return Response({"detail": "بيئة غير موجودة."}, status=status.HTTP_404_NOT_FOUND)
        membership.last_accessed_at = timezone.now()
        membership.save(update_fields=["last_accessed_at"])
        return Response({"environment_id": membership.environment_id})


class StudentEnvironmentListView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        memberships = EnvironmentMembership.objects.filter(
            user=request.user, role=EnvironmentMembership.Role.STUDENT
        ).select_related("environment", "environment__owner")
        data = StudentEnvironmentSerializer(memberships, many=True).data
        return Response(data)


class StudentEnvironmentEnterView(APIView):
    permission_classes = [IsStudent]

    def post(self, request, pk):
        membership = EnvironmentMembership.objects.filter(
            environment_id=pk, user=request.user, role=EnvironmentMembership.Role.STUDENT
        ).first()
        if not membership:
            return Response({"detail": "بيئة غير موجودة."}, status=status.HTTP_404_NOT_FOUND)
        membership.last_accessed_at = timezone.now()
        membership.save(update_fields=["last_accessed_at"])
        return Response({"environment_id": membership.environment_id})


class AddStudentView(APIView):
    """Teacher-only: pre-register a student by phone into one of the
    teacher's own environments (the piece that makes the Student Claim flow
    real). The response deliberately contains only data the caller supplied
    plus the tenant-owned membership id — see AddStudentSerializer."""

    permission_classes = [IsTeacher]
    throttle_classes = [StudentAddRateThrottle]

    def post(self, request):
        ser = AddStudentSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        membership, m_created = ser.save()
        return Response(
            {
                "membership_id": membership.id,
                "name": ser.validated_data["name"],
                "phone": ser.validated_data["phone"],
                "environment_id": membership.environment_id,
            },
            status=status.HTTP_201_CREATED if m_created else status.HTTP_200_OK,
        )
