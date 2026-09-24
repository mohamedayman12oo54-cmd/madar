from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.models import User, normalize_phone
from .models import Environment, EnvironmentMembership


def fmt_last(dt):
    if not dt:
        return None
    from django.utils import timezone
    from django.utils.timesince import timesince

    delta = timezone.now() - dt
    if delta.days == 0:
        return "آخر دخول: اليوم"
    if delta.days == 1:
        return "آخر دخول: أمس"
    return f"آخر دخول: قبل {timesince(dt, timezone.now()).split(',')[0]}"


class TeacherEnvironmentSerializer(serializers.ModelSerializer):
    last = serializers.SerializerMethodField()
    meta = serializers.CharField(source="academic_year")

    class Meta:
        model = Environment
        fields = ["id", "name", "initials", "meta", "subject_stage", "last"]

    def get_last(self, obj):
        membership = obj.memberships.filter(user=self.context["request"].user).first()
        return fmt_last(membership.last_accessed_at) if membership else None


class StudentEnvironmentSerializer(serializers.Serializer):
    """A student sees the *teacher's* identity for each environment
    they're in, matching EnvCard usage in StudentEnvSelect (initials/name
    are the teacher's, not the environment's own)."""

    id = serializers.IntegerField(source="environment.id")
    name = serializers.SerializerMethodField()
    initials = serializers.SerializerMethodField()
    meta = serializers.CharField(source="environment.academic_year")
    last = serializers.SerializerMethodField()

    def get_name(self, membership):
        return membership.environment.owner.name

    def get_initials(self, membership):
        return membership.environment.owner.initials

    def get_last(self, membership):
        return fmt_last(membership.last_accessed_at)


class AddStudentSerializer(serializers.Serializer):
    """Teacher-only: pre-register a student in one of their own
    environments. Existing users (already claimed, or pre-registered by
    another teacher) are reused rather than duplicated — phone is
    globally unique, and one student may belong to many teachers'
    environments (see StudentEnvSelect).

    Privacy contract (Phase 0 / S5): student identity is GLOBAL, so this
    endpoint must never tell a teacher anything about a global account they
    do not already own. Nothing about an existing account (its name, whether
    it has been claimed, its internal id) is ever returned or written —
    the response only echoes what the teacher just submitted plus the id of
    the tenant-owned membership row. The only remaining failure that depends
    on the phone's global state is "this number belongs to a non-student
    account"; it uses one generic message and is bounded by the
    `student-add` throttle. (Phase 2 replaces this with a tenant-owned
    roster/enrollment that removes even that.)
    """

    name = serializers.CharField(max_length=150)
    phone = serializers.CharField()
    environment_id = serializers.IntegerField()

    NOT_ADDABLE = "لا يمكن إضافة هذا الرقم كطالب."

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def validate_phone(self, value):
        digits = normalize_phone(value)
        if len(digits) < 8:
            raise serializers.ValidationError("أدخل رقم هاتف صحيح.")
        return digits

    def validate_environment_id(self, value):
        request = self.context["request"]
        env = Environment.objects.filter(id=value, owner=request.user).first()
        if not env:
            raise serializers.ValidationError("بيئة غير موجودة.")
        return env

    def validate(self, attrs):
        if User.objects.filter(phone=attrs["phone"]).exclude(role=User.Role.STUDENT).exists():
            raise serializers.ValidationError({"phone": self.NOT_ADDABLE})
        return attrs

    def save(self):
        env = self.validated_data["environment_id"]
        with transaction.atomic():
            user = User.objects.filter(phone=self.validated_data["phone"]).first()
            if not user:
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(
                            phone=self.validated_data["phone"],
                            role=User.Role.STUDENT,
                            name=self.validated_data["name"],
                            is_active=False,
                            is_verified=False,
                            password=None,  # unusable until the student claims + sets one
                        )
                except IntegrityError:
                    # Lost a race with another teacher adding the same phone.
                    user = User.objects.filter(phone=self.validated_data["phone"], role=User.Role.STUDENT).first()
                    if user is None:
                        raise serializers.ValidationError({"phone": self.NOT_ADDABLE})
            membership, m_created = EnvironmentMembership.objects.get_or_create(
                user=user, environment=env, defaults={"role": EnvironmentMembership.Role.STUDENT}
            )
        return membership, m_created
