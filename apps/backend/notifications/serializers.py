from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    """The teacher's SENT LOG. `student` is the teacher-scoped name."""

    student = serializers.SerializerMethodField()
    type_label = serializers.CharField(source="get_type_display", read_only=True)

    broadcast = serializers.SerializerMethodField()

    def get_broadcast(self, obj):
        """Present on a collapsed broadcast row: who the ONE message went to,
        so the log line reads "to Grade 1 / G1 - 12 students" instead of
        naming a single arbitrary recipient."""
        b = obj.broadcast
        if b is None:
            return None
        return {
            "id": b.id,
            "recipient_count": b.recipient_count,
            "grades": [g.name for g in b.grades.all()],
            "groups": [g.name for g in b.groups.all()],
        }

    content_item = serializers.SerializerMethodField()

    def get_content_item(self, obj):
        """Present on a collapsed video row: ONE line saying which video went
        to which grade / group - nothing else (no student, no count)."""
        c = obj.content_item
        if c is None:
            return None
        return {
            "id": c.id,
            "kind": c.kind,
            "title": c.title,
            "grades": [g.name for g in c.target_grades.all()],
            "groups": [g.name for g in c.target_groups.all()],
        }

    exam = serializers.SerializerMethodField()

    def get_exam(self, obj):
        """Present on a collapsed exam row: ONE line saying which exam went to which grade / group."""
        x = obj.exam
        if x is None:
            return None
        return {
            "id": x.id,
            "title": x.title,
            "grades": [g.name for g in x.target_grades.all()],
            "groups": [g.name for g in x.target_groups.all()],
        }

    class Meta:
        model = Notification
        fields = [
            "id", "type", "type_label", "title", "body", "student", "session",
            "broadcast", "content_item", "exam", "delivery_status", "delivery_error", "delivered_at", "created_at",
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
