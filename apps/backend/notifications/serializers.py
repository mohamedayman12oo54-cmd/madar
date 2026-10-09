from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """The teacher's SENT LOG. `student` is the teacher-scoped name."""

    student = serializers.SerializerMethodField()
    type_label = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id", "type", "type_label", "title", "body", "student", "session",
            "delivery_status", "delivery_error", "delivered_at", "created_at",
        ]

    def get_student(self, obj):
        return {"id": obj.recipient_id, "name": obj.enrollment.display_name if obj.enrollment_id else ""}


class BroadcastSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=150)
    body = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    grade_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    group_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)

    def validate_title(self, value):
        value = value.strip()
        if len(value) < 2:
            raise serializers.ValidationError("أدخل عنوانًا للرسالة.")
        return value

    def validate(self, attrs):
        if not attrs["grade_ids"] and not attrs["group_ids"]:
            raise serializers.ValidationError({"detail": "اختر صفًا أو مجموعة واحدة على الأقل."})
        return attrs
