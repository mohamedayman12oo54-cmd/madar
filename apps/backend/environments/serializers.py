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
    environments (see StudentEnvSelect)."""

    name = serializers.CharField(max_length=150)
    phone = serializers.CharField()
    environment_id = serializers.IntegerField()

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
        existing = User.objects.filter(phone=attrs["phone"]).exclude(role=User.Role.STUDENT).first()
        if existing:
            raise serializers.ValidationError({"phone": "رقم الهاتف هذا مسجَّل بالفعل بحساب من نوع آخر."})
        return attrs

    def save(self):
        env = self.validated_data["environment_id"]
        user = User.objects.filter(phone=self.validated_data["phone"]).first()
        created = False
        if not user:
            user = User.objects.create_user(
                phone=self.validated_data["phone"],
                role=User.Role.STUDENT,
                name=self.validated_data["name"],
                is_active=False,
                is_verified=False,
                password=None,  # unusable until the student claims + sets one
            )
            created = True
        membership, m_created = EnvironmentMembership.objects.get_or_create(
            user=user, environment=env, defaults={"role": EnvironmentMembership.Role.STUDENT}
        )
        return user, membership, created, m_created
