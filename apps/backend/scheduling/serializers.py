from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from rest_framework import serializers

from academics.models import Group

from .models import Schedule, SessionInstance


def _check_window(start, end):
    if end is not None and start is not None and end <= start:
        raise serializers.ValidationError({"ends_at": "وقت الانتهاء يجب أن يكون بعد وقت البداية."})


class SessionInstanceSerializer(serializers.ModelSerializer):
    """Read shape, and the shape returned after any lifecycle action."""

    group = serializers.SerializerMethodField()
    auto_close_at = serializers.DateTimeField(read_only=True)

    class Meta:
        model = SessionInstance
        fields = ["id", "group", "scheduled_at", "ends_at", "auto_close_at", "status", "opened_at", "closed_at",
                  "reopened_count", "created_at"]

    def get_group(self, obj):
        return {"id": obj.group_id, "name": obj.group.name, "grade_id": obj.group.grade_id}


class SessionInstanceCreateSerializer(serializers.ModelSerializer):
    """POST only — plans a new session. `group_id` is validated against the
    caller's own environment (GROUP OWNS SESSIONS: fixed forever after
    this — see module docstring in models.py)."""

    group_id = serializers.IntegerField(write_only=True)

    class Meta:
        model = SessionInstance
        fields = ["id", "group_id", "scheduled_at", "ends_at"]
        read_only_fields = ["id"]

    def validate(self, attrs):
        _check_window(attrs.get("scheduled_at"), attrs.get("ends_at"))
        return attrs

    def validate_group_id(self, value):
        env = self.context["request"].environment
        group = Group.objects.filter(id=value, environment=env).first()
        if not group:
            raise serializers.ValidationError("مجموعة غير موجودة.")
        return group

    def create(self, validated_data):
        validated_data["group"] = validated_data.pop("group_id")
        return super().create(validated_data)

    def to_representation(self, instance):
        return SessionInstanceSerializer(instance, context=self.context).data


class SessionInstanceRescheduleSerializer(serializers.ModelSerializer):
    """PATCH only — the sole field a session may still change once created,
    and only while still `planned` (view enforces the status check)."""

    class Meta:
        model = SessionInstance
        fields = ["scheduled_at", "ends_at"]

    def validate(self, attrs):
        start = attrs.get("scheduled_at", self.instance.scheduled_at if self.instance else None)
        end = attrs["ends_at"] if "ends_at" in attrs else (self.instance.ends_at if self.instance else None)
        _check_window(start, end)
        return attrs

    def to_representation(self, instance):
        return SessionInstanceSerializer(instance, context=self.context).data


class ScheduleSerializer(serializers.ModelSerializer):
    group = serializers.SerializerMethodField()
    weekday_label = serializers.CharField(source="get_weekday_display", read_only=True)

    class Meta:
        model = Schedule
        fields = ["id", "group", "weekday", "weekday_label", "start_time", "end_time"]

    def get_group(self, obj):
        return {"id": obj.group_id, "name": obj.group.name}


class ScheduleWriteSerializer(serializers.ModelSerializer):
    """`group_id` is validated against the caller's environment and then FIXED
    (a schedule never moves to another group)."""

    group_id = serializers.IntegerField(write_only=True, required=False)

    class Meta:
        model = Schedule
        fields = ["id", "group_id", "weekday", "start_time", "end_time"]
        read_only_fields = ["id"]

    def validate_group_id(self, value):
        env = self.context["request"].environment
        group = Group.objects.filter(id=value, environment=env).first()
        if not group:
            raise serializers.ValidationError("مجموعة غير موجودة.")
        return group

    def validate(self, attrs):
        if self.instance is None and "group_id" not in attrs:
            raise serializers.ValidationError({"group_id": "هذا الحقل مطلوب."})
        if self.instance is not None and "group_id" in attrs:
            raise serializers.ValidationError({"group_id": "لا يمكن نقل الموعد إلى مجموعة أخرى."})
        start = attrs.get("start_time", self.instance.start_time if self.instance else None)
        end = attrs["end_time"] if "end_time" in attrs else (self.instance.end_time if self.instance else None)
        if end is not None and start is not None and end <= start:
            raise serializers.ValidationError({"end_time": "وقت الانتهاء يجب أن يكون بعد وقت البداية في نفس اليوم."})
        return attrs

    def create(self, validated):
        validated["group"] = validated.pop("group_id")
        try:
            with transaction.atomic():  # savepoint: a duplicate must not poison the request transaction
                return super().create(validated)
        except IntegrityError:
            raise serializers.ValidationError({"detail": "هذا الموعد موجود بالفعل لنفس المجموعة."})

    def update(self, instance, validated):
        try:
            with transaction.atomic():
                return super().update(instance, validated)
        except IntegrityError:
            raise serializers.ValidationError({"detail": "هذا الموعد موجود بالفعل لنفس المجموعة."})

    def to_representation(self, instance):
        return ScheduleSerializer(instance, context=self.context).data


class MarkSerializer(serializers.Serializer):
    session_id = serializers.IntegerField()
    enrollment_id = serializers.IntegerField()
    status = serializers.CharField(max_length=12)


class GenerateSerializer(serializers.Serializer):
    weeks = serializers.IntegerField(min_value=1, max_value=8, default=2)
    group_id = serializers.IntegerField(required=False)


class BulkSessionSerializer(serializers.Serializer):
    """Plan the same session for several groups at once.

    A session still belongs to exactly ONE group (GROUP OWNS SESSIONS), so
    "a session for a grade" means one session per group of that grade. Targets:
      - `group_ids`            -> exactly those groups
      - `grade_id` alone       -> every group of that grade
      - `grade_id`+`group_ids` -> those groups, which must belong to the grade
    """

    scheduled_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
    grade_id = serializers.IntegerField(required=False)
    group_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list, max_length=200)

    def validate(self, attrs):
        if not attrs.get("grade_id") and not attrs["group_ids"]:
            raise serializers.ValidationError({"detail": "اختر صفًا أو مجموعة واحدة على الأقل."})
        _check_window(attrs["scheduled_at"], attrs.get("ends_at"))
        return attrs
