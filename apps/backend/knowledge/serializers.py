from rest_framework import serializers

from .models import KBDocument


class KBDocumentSerializer(serializers.ModelSerializer):
    class Meta:
        model = KBDocument
        fields = ["id", "title", "topic", "body", "status", "version", "published_at", "created_at", "updated_at"]
        read_only_fields = ["status", "version", "published_at", "created_at", "updated_at"]

    def validate_title(self, v):
        v = v.strip()
        if len(v) < 3:
            raise serializers.ValidationError("أدخل عنوانًا واضحًا (3 أحرف على الأقل).")
        return v

    def validate_body(self, v):
        v = v.strip()
        if len(v) < 20:
            raise serializers.ValidationError("محتوى المادة قصير جدًا (20 حرفًا على الأقل).")
        return v
