from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenRefreshView

from rest_framework.exceptions import APIException

from .delivery import OTPDeliveryError, deliver, mask_email, mask_phone
from .models import PendingAuth, User
from .session_revocation import revoke_all_sessions
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
    GENERIC_PENDING_ERROR,
    NewPasswordMixin,
    student_can_access,
    issue_tokens_for,
    user_public,
)
from . import lockout
from .throttles import (
    PasswordChangeRateThrottle,
    RefreshRateThrottle,
    LoginAccountRateThrottle,
    LoginRateThrottle,
    OTPRequestRateThrottle,
    OTPTargetRateThrottle,
    OTPVerifyRateThrottle,
    SensitiveRateThrottle,
    normalize_target,
)


def otp_debug_field(code):
    """Only ever populated when DEBUG is on (see settings.EXPOSE_OTP_IN_RESPONSE) —
    lets the whole OTP flow be exercised end-to-end without a real SMS/email
    provider configured. Never present in a production response."""
    return {"debug_otp": code} if settings.EXPOSE_OTP_IN_RESPONSE else {}


class OTPDeliveryFailed(APIException):
    status_code = 503
    default_code = "otp_delivery_failed"
    default_detail = "تعذّر إرسال رمز التحقق الآن. حاول مرة أخرى بعد قليل أو اختر وسيلة أخرى."


def masked_target(pending) -> str:
    """What the screen may show as 'code sent to …' — never the full address."""
    if pending.channel == "email":
        return mask_email(pending.target)
    return mask_phone(pending.target) if pending.target.isdigit() else pending.target


def send_pending_code(pending, code, strict):
    """Deliver the code over the channel the person chose.

    strict=True  — the person typed their own destination just now (teacher
                   signup, student activation): a delivery failure is shown
                   to them, and the unusable flow is discarded.
    strict=False — flows that must not reveal whether an account exists
                   (reset, guardian): failure is logged and the person can
                   press "resend"; the response is identical either way."""
    try:
        deliver(pending, code)
    except OTPDeliveryError:
        if strict:
            pending.delete()
            raise OTPDeliveryFailed()


def pending_response(pending, code, extra_message="تم إرسال رمز التحقق.", strict=False):
    send_pending_code(pending, code, strict)
    return Response(
        {"pending_id": pending.id, "target": pending.target, "channel": pending.channel,
         "target_masked": masked_target(pending), "message": extra_message, **otp_debug_field(code)},
        status=status.HTTP_200_OK,
    )


STRICT_PURPOSES = {PendingAuth.Purpose.TEACHER_SIGNUP, PendingAuth.Purpose.STUDENT_CLAIM}


def consume_pending(pending) -> bool:
    """Delete the verified pending flow in the caller's transaction and report
    whether THIS request was the one that consumed it. A pending_id is single
    use: of two concurrent requests replaying it, only one gets True."""
    deleted, _ = PendingAuth.objects.filter(pk=pending.pk, verified=True).delete()
    return deleted > 0


def _ident(request, field):
    """The submitted identifier as a normalised string, or "" when absent / not a string."""
    data = request.data
    value = data.get(field) if isinstance(data, dict) else None
    return normalize_target(value) if isinstance(value, str) else ""


GENERIC_RETRY = "حدث خطأ ما، برجاء المحاولة من جديد."


# --------- logins ----
class TeamLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle, LoginAccountRateThrottle]

    def post(self, request):
        ser = TeamLoginSerializer(data=request.data)
        lockout.guarded("login", _ident(request, "identifier"), lambda: ser.is_valid(raise_exception=True))
        user = ser.validated_data["user"]
        return Response({**issue_tokens_for(user), "user": user_public(user)})


class TeacherLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle, LoginAccountRateThrottle]

    def post(self, request):
        ser = TeacherLoginSerializer(data=request.data)
        lockout.guarded("login", _ident(request, "identifier"), lambda: ser.is_valid(raise_exception=True))
        user = ser.validated_data["user"]
        return Response({**issue_tokens_for(user), "user": user_public(user)})


class StudentLoginView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [LoginRateThrottle, LoginAccountRateThrottle]

    def post(self, request):
        ser = StudentLoginSerializer(data=request.data)
        lockout.guarded("login", _ident(request, "phone"), lambda: ser.is_valid(raise_exception=True))
        user = ser.validated_data["user"]
        return Response({**issue_tokens_for(user), "user": user_public(user)})


#-------- teacher su --
class TeacherSignupStartView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SensitiveRateThrottle, OTPTargetRateThrottle]

    def post(self, request):
        ser = TeacherSignupStartSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending, code = ser.save()
        where = "بريدك الإلكتروني" if pending.channel == "email" else "رقم هاتفك"
        return pending_response(pending, code, f"تم إرسال رمز التحقق إلى {where}.", strict=True)


class TeacherSignupEnvironmentView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        ser = TeacherSignupEnvironmentSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending = ser.validated_data["pending_id"]

        from environments.models import Environment, EnvironmentMembership

        # All-or-nothing (S7): consuming the pending flow, creating the user,
        # the environment and the owner membership are ONE transaction. Any
        # failure rolls everything back — including the consumption, so the
        # teacher can retry — and a replayed pending_id can create at most
        # one account.
        try:
            with transaction.atomic():
                if not consume_pending(pending):
                    raise serializers.ValidationError({"pending_id": GENERIC_PENDING_ERROR})
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
                # BILL-WU-014: the trial starts at exactly this atomic
                # event (account activation + Environment establishment).
                # `accounts` calls Billing's own capability rather than
                # writing a Billing table itself (BND-1); any failure here
                # rolls back the whole signup, same as everything above.
                from billing.services import start_trial

                start_trial(environment=env, activated_at=timezone.now())
        except IntegrityError:
            # Someone registered the same email/phone between signup step 1
            # and now. Nothing was written (rolled back).
            return Response(
                {"detail": "تعذّر إكمال التسجيل، الرقم أو البريد مستخدم بالفعل.", "code": "conflict"},
                status=status.HTTP_409_CONFLICT,
            )

        return Response({**issue_tokens_for(user), "user": user_public(user)}, status=status.HTTP_201_CREATED)


# --------- teacher forgot-
class TeacherForgotRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestRateThrottle, OTPTargetRateThrottle]

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
        return reset_password_and_revoke(ser)


def reset_password_and_revoke(ser):
    """Shared tail of both password-reset flows (S4): set the new password,
    consume the single-use pending flow, and revoke every existing session —
    in one transaction, so a reset never leaves old tokens alive."""
    pending = ser.validated_data["pending_id"]
    with transaction.atomic():
        user = User.objects.select_for_update().filter(id=pending.payload["user_id"]).first()
        if not user or not consume_pending(pending):
            return Response({"detail": GENERIC_RETRY}, status=status.HTTP_400_BAD_REQUEST)
        user.set_password(ser.validated_data["password"])
        user.save(update_fields=["password"])
        revoke_all_sessions(user)
    return Response({"message": "تم تغيير كلمة المرور بنجاح."})


# ------- student claim-
class StudentClaimRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestRateThrottle, OTPTargetRateThrottle]

    def post(self, request):
        ser = StudentClaimRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending, code = ser.save()
        where = "بريدك الإلكتروني" if pending.channel == "email" else "رقم هاتفك"
        return pending_response(pending, code, f"تم إرسال رمز التحقق إلى {where}.", strict=True)


class StudentClaimActivateView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        ser = StudentClaimActivateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending = ser.validated_data["pending_id"]

        with transaction.atomic():
            # Only a still-unclaimed account can be activated by a claim flow.
            user = User.objects.select_for_update().filter(
                id=pending.payload["user_id"], role=User.Role.STUDENT, is_active=False
            ).first()
            if not user or not consume_pending(pending):
                return Response({"detail": GENERIC_RETRY}, status=status.HTTP_400_BAD_REQUEST)
            # A teacher may have deactivated the student between the OTP step
            # and now — the rule is re-checked at the moment of activation.
            if not student_can_access(user):
                return Response(
                    {"detail": "تعذّر تفعيل الحساب حاليًا. تواصل مع معلّمك.", "code": "student_inactive"},
                    status=status.HTTP_403_FORBIDDEN,
                )
            fields = ["password", "is_active", "is_verified"]
            email = pending.payload.get("email")
            if email:
                # The student proved control of this address by OTP. Re-check
                # uniqueness now: someone may have registered it since step 1.
                if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                    return Response(
                        {"detail": "هذا البريد الإلكتروني مستخدم في حساب آخر.", "code": "email_in_use"},
                        status=status.HTTP_409_CONFLICT,
                    )
                user.email = email
                fields.append("email")
            user.set_password(ser.validated_data["password"])
            user.is_active = True
            user.is_verified = True
            user.save(update_fields=fields)
        # No session is issued here: the student is sent to the normal login
        # page and signs in with their phone + the password just created.
        # `phone_hint` shows only the last digits, so someone who activated by
        # email knows WHICH number to log in with without it being disclosed.
        return Response(
            {"message": "تم تفعيل حسابك. سجّل الدخول برقم هاتفك وكلمة المرور.",
             "phone_hint": mask_phone(user.phone or "")},
            status=status.HTTP_201_CREATED,
        )


#---------- student forgot --
class StudentForgotRequestView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestRateThrottle, OTPTargetRateThrottle]

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
        return reset_password_and_revoke(ser)


# ----------- OTP -----
PURPOSE_MAP = {
    "teacher-signup": PendingAuth.Purpose.TEACHER_SIGNUP,
    "teacher-reset": PendingAuth.Purpose.TEACHER_RESET,
    "student-claim": PendingAuth.Purpose.STUDENT_CLAIM,
    "student-reset": PendingAuth.Purpose.STUDENT_RESET,
    "parent-access": PendingAuth.Purpose.PARENT_ACCESS,
}


class OTPVerifyView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [OTPVerifyRateThrottle]

    def post(self, request, flow):
        purpose = PURPOSE_MAP.get(flow)
        if not purpose:
            return Response({"detail": "غير موجود."}, status=status.HTTP_404_NOT_FOUND)
        ser = OTPVerifySerializer(data=request.data, purpose=purpose)
        lockout.guarded("otp", _ident(request, "pending_id"), lambda: ser.is_valid(raise_exception=True))
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

        # Enforce the resend cap atomically (S6). resend_count is never reset,
        # so resending cannot restore the guess budget forever: a pending flow
        # allows at most MAX_ATTEMPTS * (MAX_RESENDS + 1) guesses in total.
        allowed = PendingAuth.objects.filter(
            pk=pending.pk, resend_count__lt=PendingAuth.MAX_RESENDS
        ).update(resend_count=F("resend_count") + 1)
        if not allowed:
            raise serializers.ValidationError("تجاوزت الحد الأقصى لإعادة الإرسال، برجاء البدء من جديد.")

        code = pending.set_new_otp()
        # update_fields: never write back the (stale) resend_count we loaded.
        pending.save(update_fields=["otp_hash", "otp_expires_at", "otp_attempts", "verified", "verified_at"])
        return pending_response(pending, code, "تم إرسال رمز جديد.", strict=pending.purpose in STRICT_PURPOSES)


#-------- misc ----
class MeView(APIView):
    def get(self, request):
        return Response(UserPublicSerializer(request.user).data)

    def patch(self, request):
        """Teachers (and team staff) may edit their own display name. Email
        and phone are login identities: changing them needs OTP re-verification,
        which is deferred with the OTP provider, so they are NOT editable here.
        Students never edit the global identity."""
        user = request.user
        if user.role not in (User.Role.TEACHER, User.Role.TEAM):
            return Response({"detail": "غير مسموح.", "code": "forbidden"}, status=status.HTTP_403_FORBIDDEN)
        if not isinstance(request.data, dict) or set(request.data) - {"name"}:
            return Response(
                {"detail": "يمكن تعديل الاسم فقط.", "code": "validation_error"}, status=status.HTTP_400_BAD_REQUEST
            )
        name = str(request.data.get("name", "")).strip()
        if len(name) < 2 or len(name) > 150:
            return Response(
                {"detail": "تحقق من البيانات المدخلة.", "code": "validation_error",
                 "fields": {"name": "الاسم يجب أن يكون بين حرفين و150 حرفًا."}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.name = name
        user.save(update_fields=["name"])
        return Response(UserPublicSerializer(user).data)


class ChangePasswordSerializer(NewPasswordMixin, serializers.Serializer):
    current_password = serializers.CharField(trim_whitespace=False)
    password = serializers.CharField(trim_whitespace=False)
    password2 = serializers.CharField(trim_whitespace=False)


class ChangePasswordView(APIView):
    """Authenticated password change. Requires the CURRENT password (a stolen
    access token alone cannot take over the account), then cuts off every
    existing session and returns a fresh token pair for this device only."""

    throttle_classes = [PasswordChangeRateThrottle]

    def post(self, request):
        ser = ChangePasswordSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(ser.validated_data["current_password"]):
            raise serializers.ValidationError({"current_password": "كلمة المرور الحالية غير صحيحة."})
        if ser.validated_data["current_password"] == ser.validated_data["password"]:
            raise serializers.ValidationError({"password": "اختر كلمة مرور مختلفة عن الحالية."})
        with transaction.atomic():
            user.set_password(ser.validated_data["password"])
            user.save(update_fields=["password"])
            revoke_all_sessions(user)
        return Response({**issue_tokens_for(user), "user": user_public(user)})


class SignOutEverywhereView(APIView):
    """Revoke every session of the caller (all devices), including this one."""

    def post(self, request):
        revoke_all_sessions(request.user)
        return Response(status=status.HTTP_205_RESET_CONTENT)


class ThrottledTokenRefreshView(TokenRefreshView):
    throttle_classes = [RefreshRateThrottle]


class LogoutView(APIView):
    """Blacklists the refresh token so it can no longer be used to mint
    new access tokens — the closest stateless-JWT equivalent of "log out
    everywhere this token was". The (short-lived) access token itself
    simply expires naturally.

    The refresh token itself is the credential here, so no valid access token
    is required: a client whose access token already expired can still log
    out properly instead of leaving a live refresh token behind."""

    permission_classes = [AllowAny]

    def post(self, request):
        refresh = request.data.get("refresh") if isinstance(request.data, dict) else None
        if not refresh or not isinstance(refresh, str):
            return Response({"detail": "الحقل refresh مطلوب."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            token = RefreshToken(refresh)
            token.blacklist()
        except TokenError:
            return Response({"detail": "رمز غير صالح."}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_205_RESET_CONTENT)
