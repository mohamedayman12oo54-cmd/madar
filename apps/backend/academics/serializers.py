from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.models import User, normalize_phone
from environments.models import EnvironmentMembership

from .models import Enrollment, Grade, Group


class GradeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Grade
        fields = ["id", "name", "fee_amount", "order", "created_at"]
        read_only_fields = ["id", "created_at"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def validate_fee_amount(self, value):
        if value < 0:
            raise serializers.ValidationError("قيمة الرسوم يجب أن تكون صفرًا أو أكبر.")
        return value


class GroupSerializer(serializers.ModelSerializer):
    grade_id = serializers.IntegerField(read_only=True)
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ["id", "name", "grade_id", "student_count", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_student_count(self, obj):
        return obj.enrollments.filter(is_active=True).count()


class GroupWriteSerializer(serializers.ModelSerializer):
    """Separate from GroupSerializer (which exposes grade_id read-only,
    since a group's grade — like an enrollment's — should not silently move
    across grades once students are attached to it) — `grade_id` is only
    ever set here, at creation, and validated against the caller's own
    environment."""

    grade_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Group
        fields = ["id", "name", "grade_id"]
        read_only_fields = ["id"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def validate_grade_id(self, value):
        env = self.context["request"].environment
        grade = Grade.objects.filter(id=value, environment=env).first()
        if not grade:
            raise serializers.ValidationError("صف غير موجود.")
        return grade

    def create(self, validated_data):
        validated_data["grade"] = validated_data.pop("grade_id")
        return super().create(validated_data)

    def to_representation(self, instance):
        return GroupSerializer(instance, context=self.context).data


class GroupRenameSerializer(serializers.ModelSerializer):
    """PATCH only — a Group's `grade` is fixed at creation (existing
    Enrollments rely on `enrollment.group.grade_id == enrollment.grade_id`
    always holding; see EnrollmentUpdateSerializer.validate_group)."""

    class Meta:
        model = Group
        fields = ["name"]

    def validate_name(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def to_representation(self, instance):
        return GroupSerializer(instance, context=self.context).data


class EnrollmentSerializer(serializers.ModelSerializer):
    """Read shape for GET (list/retrieve). Student's name/phone here are the
    GLOBAL identity fields (accounts.User) — safe to show because this is
    always scoped to the caller's OWN environment (TenantScopedQuerySetMixin);
    this is the "authorized enrollment relationship" the spec requires for a
    teacher to see a student's identity at all."""

    student = serializers.SerializerMethodField()
    grade = serializers.SerializerMethodField()
    group = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = ["id", "student", "grade", "group", "academic_year", "is_active", "created_at"]

    def get_student(self, obj):
        return {"id": obj.student_id, "name": obj.student.name, "phone": obj.student.phone}

    def get_grade(self, obj):
        return {"id": obj.grade_id, "name": obj.grade.name, "fee_amount": str(obj.grade.fee_amount)}

    def get_group(self, obj):
        return {"id": obj.group_id, "name": obj.group.name} if obj.group_id else None


class EnrollmentCreateSerializer(serializers.Serializer):
    """Enroll a student (existing global account or a brand-new
    pre-registered one) into the caller's OWN environment
    (`self.context["request"].environment` — resolved server-side by
    IsEnvironmentMember, never from this payload) under a given grade.

    Supersedes the old `POST /environments/students/` (Phase 0/S5) — same
    privacy contract, carried forward and strengthened: nothing about an
    EXISTING global account (its real name, whether it's claimed, its id) is
    ever read back into the response; the response only ever echoes what
    THIS caller submitted, plus their own new Enrollment id. The one
    remaining phone-shaped failure ("this number belongs to a non-student
    account") keeps its single generic message. The improvement over Phase 0:
    there is no `environment_id` field here at all — the tenant comes only
    from the header (environments/tenancy.py), so the exact bug class Phase 1
    was built to close (any environment_id a client could type into a body)
    is now structurally impossible, not just validated away.
    """

    name = serializers.CharField(max_length=150)
    phone = serializers.CharField()
    grade_id = serializers.IntegerField()
    group_id = serializers.IntegerField(required=False, allow_null=True)

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

    def validate_grade_id(self, value):
        env = self.context["request"].environment
        grade = Grade.objects.filter(id=value, environment=env).first()
        if not grade:
            raise serializers.ValidationError("صف غير موجود.")
        return grade

    def validate_group_id(self, value):
        if value is None:
            return None
        env = self.context["request"].environment
        group = Group.objects.filter(id=value, environment=env).first()
        if not group:
            raise serializers.ValidationError("مجموعة غير موجودة.")
        return group

    def validate(self, attrs):
        if User.objects.filter(phone=attrs["phone"]).exclude(role=User.Role.STUDENT).exists():
            raise serializers.ValidationError({"phone": self.NOT_ADDABLE})
        group = attrs.get("group_id")
        if group is not None and group.grade_id != attrs["grade_id"].id:
            raise serializers.ValidationError({"group_id": "المجموعة لا تنتمي لهذا الصف."})
        return attrs

    def save(self):
        env = self.context["request"].environment
        grade = self.validated_data["grade_id"]
        group = self.validated_data.get("group_id")
        phone = self.validated_data["phone"]
        with transaction.atomic():
            user = User.objects.filter(phone=phone).first()
            if not user:
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(
                            phone=phone, role=User.Role.STUDENT, name=self.validated_data["name"],
                            is_active=False, is_verified=False, password=None,
                        )
                except IntegrityError:
                    # Lost a race with another teacher adding the same phone.
                    user = User.objects.filter(phone=phone, role=User.Role.STUDENT).first()
                    if user is None:
                        raise serializers.ValidationError({"phone": self.NOT_ADDABLE})
            enrollment, created = Enrollment.objects.get_or_create(
                environment=env, student=user, defaults={"grade": grade, "group": group},
            )
            EnvironmentMembership.objects.get_or_create(
                user=user, environment=env, defaults={"role": EnvironmentMembership.Role.STUDENT},
            )
        return enrollment, created


class EnrollmentUpdateSerializer(serializers.ModelSerializer):
    """PATCH only — deliberately excludes `grade` and `academic_year`
    (immutable once set; see academics/models.py) and `student`/`environment`
    (never re-parentable via the API). Only `group` and `is_active` may move."""

    class Meta:
        model = Enrollment
        fields = ["group", "is_active"]
        extra_kwargs = {"group": {"required": False, "allow_null": True}}

    def validate_group(self, value):
        if value is None:
            return None
        env = self.context["request"].environment
        if value.environment_id != env.id:
            raise serializers.ValidationError("مجموعة غير موجودة.")
        if value.grade_id != self.instance.grade_id:
            raise serializers.ValidationError("المجموعة لا تنتمي لصف هذا الطالب.")
        return value
