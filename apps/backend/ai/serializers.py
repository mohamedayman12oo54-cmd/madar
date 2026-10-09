from rest_framework import serializers

from config.months import parse_month

from .models import AIOperation
from .providers import MAX_PROMPT_CHARS


class AIOperationSerializer(serializers.ModelSerializer):
    """Read shape for submit-response and polling. Never exposes
    requested_by/environment ids."""

    class Meta:
        model = AIOperation
        fields = ["id", "kind", "status", "prompt", "result", "suggested_state", "sources", "error", "created_at", "completed_at"]
        read_only_fields = fields


class AIOperationSubmitSerializer(serializers.Serializer):
    prompt = serializers.CharField(max_length=MAX_PROMPT_CHARS)
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)

    def validate_prompt(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("اكتب سؤالك أولًا.")
        return value

    def validate_idempotency_key(self, value):
        # Blank/absent == "no idempotency requested" (stored as NULL so the
        # partial unique constraint doesn't apply).
        return (value or "").strip() or None


class StateRecommendationSubmitSerializer(serializers.Serializer):
    enrollment_id = serializers.IntegerField()
    month = serializers.CharField()
    idempotency_key = serializers.CharField(max_length=64, required=False, allow_null=True, allow_blank=True)

    def validate_month(self, value):
        return parse_month(value)

    def validate_idempotency_key(self, value):
        return (value or "").strip() or None
