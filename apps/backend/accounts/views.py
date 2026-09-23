from django.conf import settings
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PendingAuth
from .serializers import (
    OTPVerifySerializer,
    ResendOTPSerializer,
    StudentClaimActivateSerializer,
    StudentClaimRequestSerializer,
    StudentForgotRequestSerializer,
    StudentForgotResetSerializer,
    StudentLoginSerializer,
    TeacherForgotRequestSerializer,
    TeacherForgotResetSerializer,
    TeacherLoginSerializer,
    TeacherSignupEnvironmentSerializer,
    TeacherSignupStartSerializer,
    TeamLoginSerializer,
    UserPublicSerializer,
    issue_tokens_for,
    user_public,
)
from .throttles import (
    LoginRateThrottle,
    OTPRequestRateThrottle,
    OTPVerifyRateThrottle,
    SensitiveRateThrottle,
)


def otp_debug_field(code):
    """Only ever populated when DEBUG is on (see settings.EXPOSE_OTP_IN_RESPONSE) —
    lets the whole OTP flow be exercised end-to-end without a real SMS/email
    provider configured. Never present in a production response."""
    return {"debug_otp": code} if settings.EXPOSE_OTP_IN_RESPONSE else {}


def pending_response(pending, code, extra_message="تم إرسال رمز التحقق."):
    return Response(
        {"pending_id": pending.id, "target": pending.target, "message": extra_message, **otp_debug_field(code)},
        status=status.HTTP_200_OK,
    )


# --------- logins ----
class TeamLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        ser = TeamLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data["user"]
        return Response({**issue_tokens_for(user), "user": user_public(user)})


class TeacherLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        ser = TeacherLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data["user"]
        return Response({**issue_tokens_for(user), "user": user_public(user)})


class StudentLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle]

    def post(self, request):
        ser = StudentLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = ser.validated_data["user"]
        return Response({**issue_tokens_for(user), "user": user_public(user)})


#-------- teacher su --
class TeacherSignupStartView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        ser = TeacherSignupStartSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending, code = ser.save()
        return pending_response(pending, code, "تم إرسال رمز التحقق إلى رقم هاتفك.")


class TeacherSignupEnvironmentView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        ser = TeacherSignupEnvironmentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending = ser.validated_data["pending_id"]

        from environments.models import Environment, EnvironmentMembership
        from accounts.models import User

        user = User.objects.create(
            role=User.Role.TEACHER,
            name=pending.payload["name"],
            email=pending.payload["email"],
            phone=pending.payload["phone"],
            password=pending.payload["password_hash"],
            is_active=True,
            is_verified=True,
        )
        env = Environment.objects.create(
            owner=user,
            name=ser.validated_data["name"],
            subject_stage=ser.validated_data.get("subject_stage", ""),
        )
        EnvironmentMembership.objects.create(user=user, environment=env, role=EnvironmentMembership.Role.OWNER)
        pending.delete()

        return Response({**issue_tokens_for(user), "user": user_public(user)}, status=status.HTTP_201_CREATED)


# --------- teacher forgot-
class TeacherForgotRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestRateThrottle]

    def post(self, request):
        ser = TeacherForgotRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending, code = ser.save()
        return pending_response(pending, code, "إذا كانت البيانات صحيحة، سيصلك رمز التحقق الآن.")


class TeacherForgotResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        ser = TeacherForgotResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending = ser.validated_data["pending_id"]

        from accounts.models import User

        user = User.objects.filter(id=pending.payload["user_id"]).first()
        if not user:
            return Response({"detail": "حدث خطأ ما، برجاء المحاولة من جديد."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(ser.validated_data["password"])
        user.save(update_fields=["password"])
        pending.delete()
        return Response({"message": "تم تغيير كلمة المرور بنجاح."})


# ------- student claim-
class StudentClaimRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestRateThrottle]

    def post(self, request):
        ser = StudentClaimRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending, code = ser.save()
        return pending_response(pending, code, "تم إرسال رمز التحقق إلى رقم هاتفك.")


class StudentClaimActivateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        ser = StudentClaimActivateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending = ser.validated_data["pending_id"]

        from accounts.models import User

        user = User.objects.filter(id=pending.payload["user_id"]).first()
        if not user:
            return Response({"detail": "حدث خطأ ما، برجاء المحاولة من جديد."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(ser.validated_data["password"])
        user.is_active = True
        user.is_verified = True
        user.save(update_fields=["password", "is_active", "is_verified"])
        pending.delete()
        return Response({**issue_tokens_for(user), "user": user_public(user)}, status=status.HTTP_201_CREATED)


#---------- student forgot --
class StudentForgotRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestRateThrottle]

    def post(self, request):
        ser = StudentForgotRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending, code = ser.save()
        return pending_response(pending, code, "إذا كانت البيانات صحيحة، سيصلك رمز التحقق الآن.")


class StudentForgotResetView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        ser = StudentForgotResetSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending = ser.validated_data["pending_id"]

        from accounts.models import User

        user = User.objects.filter(id=pending.payload["user_id"]).first()
        if not user:
            return Response({"detail": "حدث خطأ ما، برجاء المحاولة من جديد."}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(ser.validated_data["password"])
        user.save(update_fields=["password"])
        pending.delete()
        return Response({"message": "تم تغيير كلمة المرور بنجاح."})


# ----------- OTP -----
PURPOSE_MAP = {
    "teacher-signup": PendingAuth.Purpose.TEACHER_SIGNUP,
    "teacher-reset": PendingAuth.Purpose.TEACHER_RESET,
    "student-claim": PendingAuth.Purpose.STUDENT_CLAIM,
    "student-reset": PendingAuth.Purpose.STUDENT_RESET,
}


class OTPVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyRateThrottle]

    def post(self, request, flow):
        purpose = PURPOSE_MAP.get(flow)
        if not purpose:
            return Response({"detail": "غير موجود."}, status=status.HTTP_404_NOT_FOUND)
        ser = OTPVerifySerializer(data=request.data, purpose=purpose)
        ser.is_valid(raise_exception=True)
        return Response({"pending_id": ser.validated_data["pending_id"], "verified": True})


class OTPResendView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestRateThrottle]

    def post(self, request, flow):
        purpose = PURPOSE_MAP.get(flow)
        if not purpose:
            return Response({"detail": "غير موجود."}, status=status.HTTP_404_NOT_FOUND)
        ser = ResendOTPSerializer(data=request.data, purpose=purpose)
        ser.is_valid(raise_exception=True)
        pending = ser.validated_data["pending_id"]
        pending.resend_count += 1
        code = pending.set_new_otp()
        pending.save()
        return pending_response(pending, code, "تم إرسال رمز جديد.")


#-------- misc ----
class MeView(APIView):
    def get(self, request):
        return Response(UserPublicSerializer(request.user).data)


class LogoutView(APIView):
    """Blacklists the refresh token so it can no longer be used to mint
    new access tokens — the closest stateless-JWT equivalent of "log out
    everywhere this token was". The (short-lived) access token itself
    simply expires naturally."""

    def post(self, request):
        refresh = request.data.get("refresh")
        if not refresh:
            return Response({"detail": "الحقل refresh مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except TokenError:
            return Response({"detail": "رمز غير صالح."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)
