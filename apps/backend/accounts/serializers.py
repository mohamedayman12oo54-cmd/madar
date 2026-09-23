from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.utils import timezone
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PendingAuth, normalize_phone
from .validators import password_meets_rules

User = get_user_model()

GENERIC_LOGIN_ERROR = "بيانات الدخول غير صحيحة، حاول مرة أخرى."
GENERIC_PENDING_ERROR = "انتهت صلاحية الجلسة أو أنها غير صحيحة، برجاء البدء من جديد."


# --------------------------------------------------------------- helpers --
def issue_tokens_for(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    return {"access": str(refresh.access_token), "refresh": str(refresh)}


def user_public(user):
    return {
        "id": user.id,
        "role": user.role,
        "name": user.name,
        "email": user.email,
        "phone": user.phone,
    }


def looks_like_email(value: str) -> bool:
    return "@" in (value or "")


class UserPublicSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["id", "role", "name", "email", "phone", "is_verified"]


# ----------------------------------------------------------- password ----
class NewPasswordMixin:
    """Shared password + password2 validation matching the frontend's
    PasswordChecklist exactly (accounts/validators.py)."""

    def validate_password(self, value):
        if not password_meets_rules(value):
            raise serializers.ValidationError("كلمة المرور لا تحقق المتطلبات المطلوبة.")
        return value

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs.get("password") != attrs.get("password2"):
            raise serializers.ValidationError({"password2": "كلمتا المرور غير متطابقتين."})
        return attrs


# ------------------------------------------------------------ team login--
class TeamLoginSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        user = User.objects.filter(role=User.Role.TEAM, username__iexact=attrs["identifier"].strip()).first()
        if not user or not user.check_password(attrs["password"]) or not user.is_active:
            raise serializers.ValidationError(GENERIC_LOGIN_ERROR)
        attrs["user"] = user
        return attrs


# --------------------------------------------------------- teacher login--
class TeacherLoginSerializer(serializers.Serializer):
    identifier = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        ident = attrs["identifier"].strip()
        qs = User.objects.filter(role=User.Role.TEACHER)
        user = (
            qs.filter(email__iexact=ident).first()
            if looks_like_email(ident)
            else qs.filter(phone=normalize_phone(ident)).first()
        )
        if not user or not user.check_password(attrs["password"]) or not user.is_active:
            raise serializers.ValidationError(GENERIC_LOGIN_ERROR)
        attrs["user"] = user
        return attrs


class TeacherSignupStartSerializer(NewPasswordMixin, serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)
    password2 = serializers.CharField(trim_whitespace=False)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def validate_email(self, value):
        value = value.strip().lower()
        if User.objects.filter(email__iexact=value).exists():
            raise serializers.ValidationError("هذا البريد الإلكتروني مستخدم بالفعل.")
        return value

    def validate_phone(self, value):
        digits = normalize_phone(value)
        if len(digits) < 8:
            raise serializers.ValidationError("أدخل رقم هاتف صحيح.")
        if User.objects.filter(phone=digits).exists():
            raise serializers.ValidationError("رقم الهاتف هذا مستخدم بالفعل.")
        return digits

    def create(self, validated):
        pending = PendingAuth(
            purpose=PendingAuth.Purpose.TEACHER_SIGNUP,
            payload={
                "name": validated["name"],
                "email": validated["email"],
                "phone": validated["phone"],
                "password_hash": make_password(validated["password"]),
            },
            target=validated["phone"],
        )
        code = pending.set_new_otp()
        pending.save()
        return pending, code


class TeacherSignupEnvironmentSerializer(serializers.Serializer):
    pending_id = serializers.UUIDField()
    name = serializers.CharField(max_length=150)
    subject_stage = serializers.CharField(max_length=150, required=False, allow_blank=True)

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def validate_pending_id(self, value):
        pending = PendingAuth.objects.filter(
            id=value, purpose=PendingAuth.Purpose.TEACHER_SIGNUP, verified=True
        ).first()
        if not pending or pending.is_pending_expired():
            raise serializers.ValidationError(GENERIC_PENDING_ERROR)
        return pending


# -------------------------------------------------------- teacher forgot -
class TeacherForgotRequestSerializer(serializers.Serializer):
    identifier = serializers.CharField()

    def create(self, validated):
        ident = validated["identifier"].strip()
        qs = User.objects.filter(role=User.Role.TEACHER, is_active=True)
        user = (
            qs.filter(email__iexact=ident).first()
            if looks_like_email(ident)
            else qs.filter(phone=normalize_phone(ident)).first()
        )
        # Always create a real, working OTP flow (even with no matching
        # user) so the response never reveals whether the identifier is
        # registered — the reset step below is what actually gates access.
        pending = PendingAuth(
            purpose=PendingAuth.Purpose.TEACHER_RESET,
            payload={"user_id": user.id if user else None},
            target=ident,
        )
        code = pending.set_new_otp()
        pending.save()
        return pending, code


class TeacherForgotResetSerializer(NewPasswordMixin, serializers.Serializer):
    pending_id = serializers.UUIDField()
    password = serializers.CharField(trim_whitespace=False)
    password2 = serializers.CharField(trim_whitespace=False)

    def validate_pending_id(self, value):
        pending = PendingAuth.objects.filter(
            id=value, purpose=PendingAuth.Purpose.TEACHER_RESET, verified=True
        ).first()
        if not pending or pending.is_pending_expired() or not pending.payload.get("user_id"):
            raise serializers.ValidationError(GENERIC_PENDING_ERROR)
        return pending


# -------------------------------------------------------- student login --
class StudentLoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    password = serializers.CharField(trim_whitespace=False)

    def validate(self, attrs):
        user = User.objects.filter(role=User.Role.STUDENT, phone=normalize_phone(attrs["phone"])).first()
        if not user or not user.is_active or not user.check_password(attrs["password"]):
            raise serializers.ValidationError(GENERIC_LOGIN_ERROR)
        attrs["user"] = user
        return attrs


# -------------------------------------------------------- student claim --
class StudentClaimRequestSerializer(serializers.Serializer):
    phone = serializers.CharField()

    def validate_phone(self, value):
        digits = normalize_phone(value)
        if len(digits) < 8:
            raise serializers.ValidationError("أدخل رقم هاتف صحيح.")
        return digits

    def create(self, validated):
        user = User.objects.filter(
            role=User.Role.STUDENT, phone=validated["phone"], is_active=False
        ).first()
        if not user:
            raise serializers.ValidationError(
                {"detail": "لم نجد حساب طالب مرتبطًا بهذا الرقم.", "code": "not_found"}
            )
        pending = PendingAuth(
            purpose=PendingAuth.Purpose.STUDENT_CLAIM,
            payload={"user_id": user.id},
            target=validated["phone"],
        )
        code = pending.set_new_otp()
        pending.save()
        return pending, code


class StudentClaimActivateSerializer(NewPasswordMixin, serializers.Serializer):
    pending_id = serializers.UUIDField()
    password = serializers.CharField(trim_whitespace=False)
    password2 = serializers.CharField(trim_whitespace=False)

    def validate_pending_id(self, value):
        pending = PendingAuth.objects.filter(
            id=value, purpose=PendingAuth.Purpose.STUDENT_CLAIM, verified=True
        ).first()
        if not pending or pending.is_pending_expired():
            raise serializers.ValidationError(GENERIC_PENDING_ERROR)
        return pending


# ------------------------------------------------------- student forgot --
class StudentForgotRequestSerializer(serializers.Serializer):
    phone = serializers.CharField()

    def validate_phone(self, value):
        digits = normalize_phone(value)
        if len(digits) < 8:
            raise serializers.ValidationError("أدخل رقم هاتف صحيح.")
        return digits

    def create(self, validated):
        user = User.objects.filter(role=User.Role.STUDENT, phone=validated["phone"], is_active=True).first()
        # Same anti-enumeration shape as the teacher flow: always return a
        # real, working OTP round-trip even when no matching active
        # student exists — the reset step is what actually gates access.
        pending = PendingAuth(
            purpose=PendingAuth.Purpose.STUDENT_RESET,
            payload={"user_id": user.id if user else None},
            target=validated["phone"],
        )
        code = pending.set_new_otp()
        pending.save()
        return pending, code


class StudentForgotResetSerializer(NewPasswordMixin, serializers.Serializer):
    pending_id = serializers.UUIDField()
    password = serializers.CharField(trim_whitespace=False)
    password2 = serializers.CharField(trim_whitespace=False)

    def validate_pending_id(self, value):
        pending = PendingAuth.objects.filter(
            id=value, purpose=PendingAuth.Purpose.STUDENT_RESET, verified=True
        ).first()
        if not pending or pending.is_pending_expired() or not pending.payload.get("user_id"):
            raise serializers.ValidationError(GENERIC_PENDING_ERROR)
        return pending


# ----------------------------------------------------------- OTP verify --
class OTPVerifySerializer(serializers.Serializer):
    """Generic verify step shared by all three OTP flows — `purpose` pins
    it to the right one so a signup pending_id can't be replayed against
    the reset endpoint, etc."""

    pending_id = serializers.UUIDField()
    code = serializers.CharField(min_length=6, max_length=6)

    def __init__(self, *args, purpose=None, **kwargs):
        self.purpose = purpose
        super().__init__(*args, **kwargs)

    def validate(self, attrs):
        pending = PendingAuth.objects.filter(id=attrs["pending_id"], purpose=self.purpose).first()
        if not pending or pending.is_pending_expired():
            raise serializers.ValidationError(GENERIC_PENDING_ERROR)
        if pending.otp_attempts >= PendingAuth.MAX_ATTEMPTS:
            raise serializers.ValidationError("عدد محاولات كبير جدًا، برجاء طلب رمز جديد.")
        if pending.is_otp_expired():
            raise serializers.ValidationError("انتهت صلاحية الرمز، برجاء طلب رمز جديد.")
        if not pending.check_otp(attrs["code"]):
            pending.otp_attempts += 1
            pending.save(update_fields=["otp_attempts"])
            raise serializers.ValidationError("رمز التحقق غير صحيح.")
        pending.verified = True
        pending.verified_at = timezone.now()
        pending.save(update_fields=["verified", "verified_at"])
        attrs["pending"] = pending
        return attrs


class ResendOTPSerializer(serializers.Serializer):
    pending_id = serializers.UUIDField()

    def __init__(self, *args, purpose=None, **kwargs):
        self.purpose = purpose
        super().__init__(*args, **kwargs)

    def validate_pending_id(self, value):
        pending = PendingAuth.objects.filter(id=value, purpose=self.purpose).first()
        if not pending or pending.is_pending_expired():
            raise serializers.ValidationError(GENERIC_PENDING_ERROR)
        return pending
