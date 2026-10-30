from django.db import IntegrityError, transaction
from rest_framework import serializers

from accounts.models import User
from accounts.phones import digits_only
from accounts.serializers import clean_phone
from billing.entitlements import StudentCapReached, student_cap_locked
from environments.models import EnvironmentMembership

from .access import count_for_cap
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
    schedules = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ["id", "name", "grade_id", "student_count", "schedules", "created_at"]
        read_only_fields = ["id", "created_at"]

    def get_student_count(self, obj):
        return obj.member_enrollments.filter(is_active=True).count()

    def get_schedules(self, obj):
        """The weekly slots this group meets on, so the UI can name the days
        ("السبت، الثلاثاء") instead of showing a group with no timing."""
        return [
            {"id": s.id, "weekday": s.weekday, "weekday_label": s.get_weekday_display(),
             "start_time": s.start_time}
            for s in obj.schedules.all()
        ]


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


NOT_ADDABLE = "لا يمكن إضافة هذا الرقم كطالب."
PHONE_IN_USE = "لا يمكن استخدام هذا الرقم."
# Product-owner decision (Oct 2026): a student belongs to ONE group only.
MAX_GROUPS_PER_STUDENT = 1


class EnrollmentSerializer(serializers.ModelSerializer):
    """Read shape for GET (list/retrieve). Names shown here are the TEACHER-
    SCOPED `student_name` (never another teacher's wording of a shared global
    account); the phone is the global login identity, shown only because this
    is always scoped to the caller's OWN environment (TenantScopedQuerySetMixin)
    — the "authorized enrollment relationship" the spec requires."""

    student = serializers.SerializerMethodField()
    grade = serializers.SerializerMethodField()
    groups = serializers.SerializerMethodField()
    can_edit_phone = serializers.SerializerMethodField()

    class Meta:
        model = Enrollment
        fields = [
            "id", "student", "grade", "groups", "academic_year", "is_active",
            "parent_name", "parent_phone", "can_edit_phone", "qr_token", "created_at",
        ]

    def get_student(self, obj):
        return {"id": obj.student_id, "name": obj.display_name, "phone": obj.student.phone}

    def get_grade(self, obj):
        return {"id": obj.grade_id, "name": obj.grade.name, "fee_amount": str(obj.grade.fee_amount)}

    def get_groups(self, obj):
        return [{"id": g.id, "name": g.name} for g in obj.groups.all()]

    def get_can_edit_phone(self, obj):
        # Only a typo-fix on an account nobody has claimed and no other
        # teacher uses. A claimed or shared phone is a global identity.
        return (not obj.student.is_active) and obj.student.enrollments.count() == 1


def _resolve_groups(env, ids, grade):
    """Validate group ids against the caller's environment and the enrollment's
    GRADE (INV-4). Returns the Group rows."""
    ids = list(dict.fromkeys(ids))  # de-duplicate, keep order
    if len(ids) > MAX_GROUPS_PER_STUDENT:
        raise serializers.ValidationError({"group_ids": "يمكن إضافة الطالب إلى مجموعة واحدة فقط."})
    groups = list(Group.objects.filter(environment=env, id__in=ids))
    if len(groups) != len(ids):
        raise serializers.ValidationError({"group_ids": "مجموعة غير موجودة."})
    if any(g.grade_id != grade.id for g in groups):
        raise serializers.ValidationError({"group_ids": "المجموعة لا تنتمي لصف هذا الطالب."})
    return groups


class _ParentFieldsMixin:
    def validate_parent_name(self, value):
        return value.strip()

    def validate_parent_phone(self, value):
        """Normalises to the canonical form. `clean_phone` raises on anything
        that is not a real number, so a typo cannot be stored."""
        value = (value or "").strip()
        return clean_phone(value) if value else ""


class EnrollmentCreateSerializer(_ParentFieldsMixin, serializers.Serializer):
    """Enroll a student (existing global account or a brand-new pre-registered
    one) into the caller's OWN environment (`request.environment`, resolved
    server-side by IsEnvironmentMember — never from this payload).

    Privacy contract (kept from Phase 0): nothing about an EXISTING global
    account (its real name, whether it is claimed, its id) is ever read back;
    the response only echoes what THIS caller submitted plus their own
    Enrollment id. A phone that belongs to a non-student account gets one
    generic message. The global account's name is NEVER overwritten by a
    second teacher.
    """

    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=32)
    grade_id = serializers.IntegerField()
    group_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    is_active = serializers.BooleanField(required=False, default=True)
    parent_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    # Mandatory at enrolment: the guardian number is the only contact Madar
    # has for a student who has not claimed their account yet.
    parent_phone = serializers.CharField(max_length=32, required=True, allow_blank=False)

    def validate_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("أدخل اسم الطالب (حرفان على الأقل).")
        return value

    def validate_phone(self, value):
        return clean_phone(value)

    def validate_grade_id(self, value):
        env = self.context["request"].environment
        grade = Grade.objects.filter(id=value, environment=env).first()
        if not grade:
            raise serializers.ValidationError("صف غير موجود.")
        return grade

    def validate(self, attrs):
        if User.objects.filter(phone=attrs["phone"]).exclude(role=User.Role.STUDENT).exists():
            raise serializers.ValidationError({"phone": NOT_ADDABLE})
        env = self.context["request"].environment
        attrs["groups"] = _resolve_groups(env, attrs.get("group_ids", []), attrs["grade_id"])
        return attrs

    def save(self):
        env = self.context["request"].environment
        v = self.validated_data
        phone = v["phone"]
        with transaction.atomic():
            user = User.objects.filter(phone=phone).first()
            if not user:
                try:
                    with transaction.atomic():
                        user = User.objects.create_user(
                            phone=phone, role=User.Role.STUDENT, name=v["name"],
                            is_active=False, is_verified=False, password=None,
                        )
                except IntegrityError:
                    # Lost a race with another teacher adding the same phone.
                    user = User.objects.filter(phone=phone, role=User.Role.STUDENT).first()
                    if user is None:
                        raise serializers.ValidationError({"phone": NOT_ADDABLE})

            # BILL-WU-012: an idempotent re-add of a student already enrolled
            # here (the `created=False` path below) is never a NEW addition
            # and must never be blocked by the cap (this unit's own Failure
            # modes). Only check when this really will insert a new row —
            # checked and locked inside this SAME transaction as the insert
            # below, so two concurrent adds at cap - 1 cannot both pass.
            is_new_addition = not Enrollment.objects.filter(environment=env, student=user).exists()
            if is_new_addition and v["is_active"]:
                # An inactive new enrollment (`is_active=False`) never
                # changes `count_for_cap`'s own count, so it is never
                # blocked by the cap either — only an addition that will
                # actually count.
                cap = student_cap_locked(env)
                if cap is not None and count_for_cap(env) >= cap:
                    raise StudentCapReached()

            enrollment, created = Enrollment.objects.get_or_create(
                environment=env, student=user,
                defaults={
                    "grade": v["grade_id"], "student_name": v["name"], "is_active": v["is_active"],
                    "parent_name": v["parent_name"], "parent_phone": v["parent_phone"],
                },
            )
            if created:
                enrollment.groups.set(v["groups"])
            EnvironmentMembership.objects.get_or_create(
                user=user, environment=env, defaults={"role": EnvironmentMembership.Role.STUDENT},
            )
        return enrollment, created


class EnrollmentUpdateSerializer(_ParentFieldsMixin, serializers.Serializer):
    """PATCH only. Deliberately excludes `grade`/`academic_year` (immutable —
    INV-3) and `student`/`environment` (never re-parentable).

    Editable by the teacher, all TEACHER-SCOPED except `phone`:
      student_name, parent_name, parent_phone, group_ids, is_active
    `phone` is the student's GLOBAL login identity, so it is only correctable
    while the account is unclaimed AND this is the student's only enrollment
    (a typo fix) — otherwise one teacher could hijack or lock out an account
    other teachers or the student rely on."""

    student_name = serializers.CharField(max_length=150, required=False)
    parent_name = serializers.CharField(max_length=150, required=False, allow_blank=True)
    parent_phone = serializers.CharField(max_length=32, required=False, allow_blank=True)
    phone = serializers.CharField(max_length=32, required=False)
    group_ids = serializers.ListField(child=serializers.IntegerField(), required=False)
    is_active = serializers.BooleanField(required=False)

    def validate_student_name(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("أدخل اسم الطالب (حرفان على الأقل).")
        return value

    def validate_phone(self, value):
        return clean_phone(value)

    def validate(self, attrs):
        if "group_ids" in attrs:
            env = self.context["request"].environment
            attrs["groups"] = _resolve_groups(env, attrs["group_ids"], self.instance.grade)
        return attrs

    def update(self, instance, validated):
        user = instance.student
        with transaction.atomic():
            new_phone = validated.get("phone")
            if new_phone and new_phone != user.phone:
                if user.is_active or user.enrollments.count() != 1:
                    raise serializers.ValidationError(
                        {"phone": "لا يمكن تعديل الرقم بعد تفعيل الطالب لحسابه أو ارتباطه بمعلّم آخر."}
                    )
                if User.objects.filter(phone=new_phone).exclude(pk=user.pk).exists():
                    raise serializers.ValidationError({"phone": PHONE_IN_USE})
                user.phone = new_phone
                try:
                    with transaction.atomic():
                        user.save(update_fields=["phone"])
                except IntegrityError:
                    raise serializers.ValidationError({"phone": PHONE_IN_USE})

            for field in ("student_name", "parent_name", "parent_phone"):
                if field in validated:
                    setattr(instance, field, validated[field])
            was_active = instance.is_active
            if "is_active" in validated:
                activating = validated["is_active"] and not was_active
                if activating:
                    # BILL-WU-012: re-activation is gated exactly like a new
                    # addition — deactivating (or no change) never is (this
                    # unit's own AC-2). Locked and checked inside this SAME
                    # transaction as the save below.
                    cap = student_cap_locked(instance.environment)
                    if cap is not None and count_for_cap(instance.environment) >= cap:
                        raise StudentCapReached()
                instance.is_active = validated["is_active"]
            instance.save()
            if "groups" in validated:
                instance.groups.set(validated["groups"])

            if was_active and not instance.is_active and user.is_active:
                # Deactivated by this teacher. If no other teacher keeps the
                # student active, cut off every session they hold right now.
                from academics.access import student_has_active_enrollment
                from accounts.session_revocation import revoke_all_sessions

                if not student_has_active_enrollment(user):
                    revoke_all_sessions(user)
        return instance
