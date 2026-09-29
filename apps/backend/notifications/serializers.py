from rest_framework import serializers

from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    session_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = Notification
        fields = [
            "id", "type", "title", "body", "session_id",
            "delivery_status", "read_at", "created_at",
        ]
        read_only_fields = fields
