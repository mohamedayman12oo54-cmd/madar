from rest_framework import serializers

from academics.models import Enrollment

from .models import Payment


class PaymentSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()

    class Meta:
        model = Payment
        fields = ["id", "enrollment", "student", "amount", "paid_at", "note", "created_at"]

    def get_student(self, obj):
        return {"id": obj.enrollment.student_id, "name": obj.enrollment.student.name}


class PaymentCreateSerializer(serializers.ModelSerializer):
    enrollment_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = Payment
        fields = ["id", "enrollment_id", "amount", "paid_at", "note"]
        extra_kwargs = {"paid_at": {"required": False}, "note": {"required": False}}

    def validate_enrollment_id(self, value):
        env = self.context["request"].environment
        enrollment = Enrollment.objects.filter(id=value, environment=env).first()
        if not enrollment:
            raise serializers.ValidationError("تسجيل غير موجود.")
        return enrollment

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("قيمة الدفعة يجب أن تكون أكبر من صفر.")
        return value

    def create(self, validated_data):
        validated_data["enrollment"] = validated_data.pop("enrollment_id")
        return super().create(validated_data)

    def to_representation(self, instance):
        return PaymentSerializer(instance, context=self.context).data


class PaymentUpdateSerializer(serializers.ModelSerializer):
    """PATCH only — `enrollment` is fixed at creation (moving a payment to a
    different student is a correction better made by deleting and
    re-entering it, so the ledger stays legible)."""

    class Meta:
        model = Payment
        fields = ["amount", "paid_at", "note"]
        extra_kwargs = {"amount": {"required": False}, "paid_at": {"required": False}, "note": {"required": False}}

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("قيمة الدفعة يجب أن تكون أكبر من صفر.")
        return value

    def to_representation(self, instance):
        return PaymentSerializer(instance, context=self.context).data


class EnrollmentFinancialSummarySerializer(serializers.Serializer):
    """One row of GET /financials/summary/ — one per Enrollment in scope."""

    enrollment_id = serializers.IntegerField()
    student = serializers.SerializerMethodField()
    grade_id = serializers.IntegerField()
    grade_name = serializers.CharField()
    fee_amount = serializers.DecimalField(max_digits=10, decimal_places=2)
    paid_total = serializers.DecimalField(max_digits=10, decimal_places=2)
    outstanding = serializers.DecimalField(max_digits=10, decimal_places=2)

    def get_student(self, obj):
        return {"id": obj["student_id"], "name": obj["student_name"]}
