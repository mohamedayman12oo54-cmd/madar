from rest_framework import serializers

from config.months import parse_month

from .models import MonthlyRating, PrivateNote, StudentState


class NoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PrivateNote
        fields = ["id", "enrollment", "body", "created_at", "updated_at"]
        read_only_fields = ["id", "enrollment", "created_at", "updated_at"]

    def validate_body(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("اكتب الملاحظة أولًا.")
        return value


class NoteCreateSerializer(NoteSerializer):
    enrollment_id = serializers.IntegerField(write_only=True)

    class Meta(NoteSerializer.Meta):
        fields = NoteSerializer.Meta.fields + ["enrollment_id"]


class _MonthMixin(serializers.Serializer):
    enrollment_id = serializers.IntegerField()
    month = serializers.CharField()

    def validate_month(self, value):
        return parse_month(value)


class RatingUpsertSerializer(_MonthMixin):
    value = serializers.IntegerField(min_value=1, max_value=5)


class RatingPublishSerializer(_MonthMixin):
    pass


class RatingPublishAllSerializer(serializers.Serializer):
    month = serializers.CharField()
    grade_id = serializers.IntegerField(required=False)
    group_id = serializers.IntegerField(required=False)

    def validate_month(self, value):
        return parse_month(value)


class StateUpsertSerializer(_MonthMixin):
    state = serializers.ChoiceField(choices=StudentState.State.choices)
