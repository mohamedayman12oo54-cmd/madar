from rest_framework import serializers

from academics.models import Grade

from .models import ContentItem
from .video import VideoRefError, describe_video, validate_video


class ContentItemSerializer(serializers.ModelSerializer):
    """Read shape. `video` is provider-neutral (content/video.py) — the
    frontend never learns what a YouTube/Vimeo URL looks like, and the raw
    stored `video_ref` is deliberately not exposed."""

    grade = serializers.SerializerMethodField()
    video = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = ["id", "grade", "title", "description", "video", "created_at"]

    def get_grade(self, obj):
        return {"id": obj.grade_id, "name": obj.grade.name} if obj.grade_id else None

    def get_video(self, obj):
        return describe_video(obj.video_provider, obj.video_ref)


class ContentItemWriteSerializer(serializers.ModelSerializer):
    """Create + PATCH. `grade_id` is validated against the caller's own
    environment (null = general content, not tied to a grade)."""

    grade_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    video_provider = serializers.ChoiceField(choices=ContentItem._meta.get_field("video_provider").choices, required=False)
    video_ref = serializers.CharField(required=False, allow_blank=True, max_length=255)

    class Meta:
        model = ContentItem
        fields = ["id", "grade_id", "title", "description", "video_provider", "video_ref"]
        read_only_fields = ["id"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def validate_grade_id(self, value):
        if value is None:
            return None
        env = self.context["request"].environment
        grade = Grade.objects.filter(id=value, environment=env).first()
        if not grade:
            raise serializers.ValidationError("صف غير موجود.")
        return grade

    def validate(self, attrs):
        # On PATCH either half may be omitted — fall back to what's stored.
        provider = attrs.get("video_provider", getattr(self.instance, "video_provider", "none"))
        ref = attrs.get("video_ref", getattr(self.instance, "video_ref", ""))
        if "video_provider" in attrs and attrs["video_provider"] == "none" and "video_ref" not in attrs:
            ref = ""
        try:
            attrs["video_ref"] = validate_video(provider, ref)
        except VideoRefError as e:
            raise serializers.ValidationError({"video_ref": str(e)})
        attrs["video_provider"] = provider
        return attrs

    def create(self, validated_data):
        validated_data["grade"] = validated_data.pop("grade_id", None)
        return super().create(validated_data)

    def update(self, instance, validated_data):
        if "grade_id" in validated_data:
            validated_data["grade"] = validated_data.pop("grade_id")
        return super().update(instance, validated_data)

    def to_representation(self, instance):
        return ContentItemSerializer(instance, context=self.context).data
