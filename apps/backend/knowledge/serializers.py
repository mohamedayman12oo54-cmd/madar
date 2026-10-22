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

    def update(self, instance, validated_data):
        # A PUBLISHED document is what the Study Assistant is grounded on, and answers cite the version they
        # used. Changing its text in place without changing its version would let two different texts share
        # one citation, so a real content change to a published document bumps the version (a save that
        # changes nothing does not). Drafts are not authoritative and keep their version.
        changed = any(getattr(instance, field) != value for field, value in validated_data.items())
        if changed and instance.status == KBDocument.Status.PUBLISHED:
            validated_data["version"] = instance.version + 1
        return super().update(instance, validated_data)
