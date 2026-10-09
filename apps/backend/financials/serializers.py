from rest_framework import serializers

from config.months import parse_month

from .models import MonthlyPayment


class PaymentUpsertSerializer(serializers.Serializer):
    """The client sends ONLY (enrollment, month, status, note). The amount is
    decided by the server from the grade fee — see models.py."""

    enrollment_id = serializers.IntegerField()
    month = serializers.CharField()
    status = serializers.ChoiceField(choices=MonthlyPayment.Status.choices)
    note = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")

    def validate_month(self, value):
        return parse_month(value)

    def validate_note(self, value):
        return value.strip()


class PaymentHistorySerializer(serializers.ModelSerializer):
    month = serializers.SerializerMethodField()

    class Meta:
        model = MonthlyPayment
        fields = ["id", "month", "status", "amount", "paid_at", "note"]

    def get_month(self, obj):
        return obj.month.strftime("%Y-%m")
