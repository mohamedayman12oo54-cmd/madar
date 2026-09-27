from rest_framework import serializers

from academics.models import Enrollment
from scheduling.models import SessionInstance

from .models import Rating, TeacherNote


class _EnrollmentSessionValidationMixin:
    """Shared validate_enrollment_id/validate_session_id for the two create
    serializers below — same cross-check AttendanceRecord/SessionInstance
    already enforce at the model layer (defense-in-depth); this is the real
    (API-level) enforcement point."""

    def validate_enrollment_id(self, value):
        env = self.context["request"].environment
        enrollment = Enrollment.objects.filter(id=value, environment=env).first()
        if not enrollment:
            raise serializers.ValidationError("تسجيل غير موجود.")
        return enrollment

    def validate_session_id(self, value):
        if value is None:
            return None
        env = self.context["request"].environment
        session = SessionInstance.objects.filter(id=value, environment=env).first()
        if not session:
            raise serializers.ValidationError("جلسة غير موجودة.")
        return session

    def validate(self, attrs):
        session = attrs.get("session_id")
        enrollment = attrs.get("enrollment_id")
        if session is not None and enrollment is not None and session.group_id != enrollment.group_id:
            raise serializers.ValidationError({"session_id": "الجلسة لا تخص مجموعة هذا الطالب."})
        return attrs


class TeacherNoteSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()

    class Meta:
        model = TeacherNote
        fields = ["id", "enrollment", "session", "student", "body", "created_at"]

    def get_student(self, obj):
        return {"id": obj.enrollment.student_id, "name": obj.enrollment.student.name}


class TeacherNoteCreateSerializer(_EnrollmentSessionValidationMixin, serializers.ModelSerializer):
    enrollment_id = serializers.IntegerField(write_only=True)
    session_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = TeacherNote
        fields = ["id", "enrollment_id", "session_id", "body"]

    def validate_body(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def create(self, validated_data):
        validated_data["enrollment"] = validated_data.pop("enrollment_id")
        validated_data["session"] = validated_data.pop("session_id", None)
        return super().create(validated_data)

    def to_representation(self, instance):
        return TeacherNoteSerializer(instance, context=self.context).data


class TeacherNoteUpdateSerializer(serializers.ModelSerializer):
    """PATCH only — `body` is the only thing a note may change; its
    enrollment/session pairing is fixed at creation."""

    class Meta:
        model = TeacherNote
        fields = ["body"]

    def validate_body(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def to_representation(self, instance):
        return TeacherNoteSerializer(instance, context=self.context).data


class RatingSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()

    class Meta:
        model = Rating
        fields = ["id", "enrollment", "session", "student", "value", "created_at"]

    def get_student(self, obj):
        return {"id": obj.enrollment.student_id, "name": obj.enrollment.student.name}


class RatingCreateSerializer(_EnrollmentSessionValidationMixin, serializers.ModelSerializer):
    enrollment_id = serializers.IntegerField(write_only=True)
    session_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)

    class Meta:
        model = Rating
        fields = ["id", "enrollment_id", "session_id", "value"]

    def validate_value(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("التقييم يجب أن يكون رقمًا من 1 إلى 5.")
        return value

    def create(self, validated_data):
        validated_data["enrollment"] = validated_data.pop("enrollment_id")
        validated_data["session"] = validated_data.pop("session_id", None)
        return super().create(validated_data)

    def to_representation(self, instance):
        return RatingSerializer(instance, context=self.context).data


class RatingUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Rating
        fields = ["value"]

    def validate_value(self, value):
        if not (1 <= value <= 5):
            raise serializers.ValidationError("التقييم يجب أن يكون رقمًا من 1 إلى 5.")
        return value

    def to_representation(self, instance):
        return RatingSerializer(instance, context=self.context).data
