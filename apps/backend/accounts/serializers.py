from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import make_password
from django.db.models import F
from django.utils import timezone
from rest_framework import exceptions, serializers
from rest_framework_simplejwt.tokens import RefreshToken

from .models import PendingAuth, normalize_phone, supersede_pending  # noqa: F401  (re-exported for tests)
from .phones import PhoneError, canonical_phone, try_canonical_phone
from .validators import password_meets_rules

User = get_user_model()

GENERIC_LOGIN_ERROR = "بيانات الدخول غير صحيحة، حاول مرة أخرى."
GENERIC_PENDING_ERROR = "انتهت صلاحية الجلسة أو أنها غير صحيحة، برجاء البدء من جديد."


# --------------------------------------------------------------- helpers --
def issue_tokens_for(user):
    refresh = RefreshToken.for_user(user)
    refresh["role"] = user.role
    # Session version: lets a password reset invalidate every token issued
    # before it (see accounts/authentication.py).
    refresh["sv"] = user.session_version
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


def clean_phone(value: str) -> str:
    """Strict, country-aware validation (accounts/phones.py): the API always
    requires the country code. Returns the canonical digits-only number."""
    try:
        return canonical_phone(value)
    except PhoneError as exc:
        raise serializers.ValidationError(exc.message_ar)


def student_can_access(user) -> bool:
    """A student may use Madar only while at least one teacher keeps them
    ACTIVE. Deactivated everywhere => cannot claim, log in, or use any token,
    until a teacher (this one or another) activates them again."""
    from academics.access import student_has_active_enrollment

    return student_has_active_enrollment(user)


class StudentInactive(exceptions.APIException):
    """400 with a stable machine code. A dedicated exception (not a dict
    ValidationError) because serializer-level dict errors get list-wrapped by
    DRF, which would hand the frontend `code: ["student_inactive"]`."""

    status_code = 400
    default_code = "student_inactive"
    default_detail = "تم إيقاف حسابك لدى معلّمك حاليًا. تواصل مع معلّمك لإعادة التفعيل."


STUDENT_INACTIVE = "تم إيقاف حسابك لدى معلّمك حاليًا. تواصل مع معلّمك لإعادة التفعيل."
CLAIM_NOT_FOUND = "لم نتمكن من التحقق من بياناتك. تأكد من كود الطالب ومن الرقم المسجّل لدى معلّمك، أو تواصل مع معلّمك."
CLAIM_EMAIL_IN_USE = "هذا البريد الإلكتروني مستخدم في حساب آخر، استخدم بريدًا آخر أو فعّل بالرقم."


def normalize_student_code(raw: str) -> str:
    """Badge codes are typed by hand: ignore case, spaces and dashes."""
    return "".join(ch for ch in str(raw or "").upper() if ch.isalnum())


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
        phone = None if looks_like_email(ident) else try_canonical_phone(ident, default_country="EG")
        user = (
            qs.filter(email__iexact=ident).first()
            if looks_like_email(ident)
            else (qs.filter(phone=phone).first() if phone else None)
        )
        if not user or not user.check_password(attrs["password"]) or not user.is_active:
            raise serializers.ValidationError(GENERIC_LOGIN_ERROR)
        attrs["user"] = user
        return attrs


class TeacherSignupStartSerializer(NewPasswordMixin, serializers.Serializer):
    name = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    phone = serializers.CharField()
    # Where the teacher wants the verification code: the registered phone
    # (SMS) or the registered email.
    otp_channel = serializers.ChoiceField(choices=["phone", "email"], required=False, default="phone")
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
        digits = clean_phone(value)
        if User.objects.filter(phone=digits).exists():
            raise serializers.ValidationError("رقم الهاتف هذا مستخدم بالفعل.")
        return digits

    def create(self, validated):
        channel = validated.get("otp_channel", "phone")
        # Either destination may have been used by an earlier attempt for the
        # same person: invalidate both so only the newest code is ever live.
        supersede_pending(PendingAuth.Purpose.TEACHER_SIGNUP, validated["phone"])
        supersede_pending(PendingAuth.Purpose.TEACHER_SIGNUP, validated["email"])
        pending = PendingAuth(
            purpose=PendingAuth.Purpose.TEACHER_SIGNUP,
            payload={
                "name": validated["name"],
                "email": validated["email"],
                "phone": validated["phone"],
                "password_hash": make_password(validated["password"]),
            },
            channel=channel,
            target=validated["email"] if channel == "email" else validated["phone"],
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
        phone = None if looks_like_email(ident) else try_canonical_phone(ident, default_country="EG")
        user = (
            qs.filter(email__iexact=ident).first()
            if looks_like_email(ident)
            else (qs.filter(phone=phone).first() if phone else None)
        )
        # Always create a real, working OTP flow (even with no matching
        # user) so the response never reveals whether the identifier is
        # registered — the reset step below is what actually gates access.
        supersede_pending(PendingAuth.Purpose.TEACHER_RESET, ident)
        pending = PendingAuth(
            purpose=PendingAuth.Purpose.TEACHER_RESET,
            payload={"user_id": user.id if user else None},
            channel="email" if looks_like_email(ident) else "phone",
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
        phone = try_canonical_phone(attrs["phone"])
        user = User.objects.filter(role=User.Role.STUDENT, phone=phone).first() if phone else None
        if not user or not user.is_active or not user.check_password(attrs["password"]):
            raise serializers.ValidationError(GENERIC_LOGIN_ERROR)
        # Credentials are correct at this point, so telling the student WHY
        # they are blocked leaks nothing to anyone else.
        if not student_can_access(user):
            raise StudentInactive()
        attrs["user"] = user
        return attrs


# -------------------------------------------------------- student claim --
class StudentClaimRequestSerializer(serializers.Serializer):
    """Activation, step 1. TWO independent proofs are required:

      1. control of a contact — the student's phone (SMS) or an email of their
         choice — proven later by the OTP;
      2. membership — the STUDENT CODE their teacher gave them (the badge
         code of their enrolment), proving the person really is a student of
         some teacher in the system.

    The code is checked BEFORE anything is sent, so nobody can use this
    endpoint to push SMS/email to arbitrary numbers or addresses, and every
    failure (unknown code, wrong phone, already activated, deactivated) is the
    same message — it is not an oracle for codes, numbers or accounts."""

    channel = serializers.ChoiceField(choices=["phone", "email"])
    student_code = serializers.CharField(max_length=32)
    phone = serializers.CharField(required=False, allow_blank=True)
    email = serializers.EmailField(required=False, allow_blank=True)

    def validate(self, attrs):
        attrs = super().validate(attrs)
        if attrs["channel"] == "phone":
            if not (attrs.get("phone") or "").strip():
                raise serializers.ValidationError({"phone": "أدخل رقم الهاتف."})
            attrs["phone"] = clean_phone(attrs["phone"])
            attrs.pop("email", None)
        else:
            if not (attrs.get("email") or "").strip():
                raise serializers.ValidationError({"email": "أدخل البريد الإلكتروني."})
            attrs["email"] = attrs["email"].strip().lower()
            attrs.pop("phone", None)
        attrs["student_code"] = normalize_student_code(attrs["student_code"])
        if not attrs["student_code"]:
            raise serializers.ValidationError({"student_code": "أدخل كود الطالب."})
        return attrs

    def create(self, validated):
        from academics.models import Enrollment

        channel = validated["channel"]
        enrollment = (
            Enrollment.objects.select_related("student")
            .filter(
                qr_token=validated["student_code"],
                is_active=True,
                student__role=User.Role.STUDENT,
                student__is_active=False,
            )
            .first()
        )
        user = enrollment.student if enrollment else None
        if not user or not student_can_access(user):
            raise serializers.ValidationError({"detail": CLAIM_NOT_FOUND, "code": "not_found"})
        # Phone channel: the number must be the one on the student's record
        # (it is also their login). Email channel: any email the student
        # controls — the code already identified the account.
        if channel == "phone" and user.phone != validated["phone"]:
            raise serializers.ValidationError({"detail": CLAIM_NOT_FOUND, "code": "not_found"})
        if channel == "email" and User.objects.filter(email__iexact=validated["email"]).exclude(pk=user.pk).exists():
            raise serializers.ValidationError({"detail": CLAIM_EMAIL_IN_USE, "code": "email_in_use"})

        target = validated["phone"] if channel == "phone" else validated["email"]
        # One live activation per student, whichever channel was used before.
        for old in filter(None, (user.phone, user.email, target)):
            supersede_pending(PendingAuth.Purpose.STUDENT_CLAIM, old)
        payload = {"user_id": user.id}
        if channel == "email":
            payload["email"] = target
        pending = PendingAuth(
            purpose=PendingAuth.Purpose.STUDENT_CLAIM,
            payload=payload,
            channel=channel,
            target=target,
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
        return clean_phone(value)

    def create(self, validated):
        user = User.objects.filter(role=User.Role.STUDENT, phone=validated["phone"], is_active=True).first()
        if user and not student_can_access(user):
            user = None  # deactivated everywhere: same silent outcome as "no such account"
        # Same anti-enumeration shape as the teacher flow: always return a
        # real, working OTP round-trip even when no matching active
        # student exists — the reset step is what actually gates access.
        supersede_pending(PendingAuth.Purpose.STUDENT_RESET, validated["phone"])
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

        # Atomically CLAIM one attempt *before* comparing the code. The
        # conditional UPDATE is a single statement, so concurrent requests
        # cannot each read "4 attempts used" and all get a free guess (the old
        # read-modify-write allowed more than MAX_ATTEMPTS parallel guesses).
        # Every guess — right or wrong — consumes an attempt.
        claimed = PendingAuth.objects.filter(
            pk=pending.pk, otp_attempts__lt=PendingAuth.MAX_ATTEMPTS
        ).update(otp_attempts=F("otp_attempts") + 1)
        if not claimed:
            raise serializers.ValidationError("عدد محاولات كبير جدًا، برجاء طلب رمز جديد.")

        if not pending.check_otp(attrs["code"]):
            raise serializers.ValidationError("رمز التحقق غير صحيح.")

        PendingAuth.objects.filter(pk=pending.pk).update(verified=True, verified_at=timezone.now())
        pending.refresh_from_db()
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
