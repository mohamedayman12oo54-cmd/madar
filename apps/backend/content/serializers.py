from rest_framework import serializers

from academics.models import Enrollment, Grade, Group

from .models import ContentItem
from .video import VideoRefError, describe_video, validate_video

MAX_TARGETS = 500
MAX_SUMMARY_CHARS = 20000


class ContentItemSerializer(serializers.ModelSerializer):
    """Read shape. `video` is provider-neutral (content/video.py); the raw
    stored `video_ref` is never exposed."""

    video = serializers.SerializerMethodField()
    targets = serializers.SerializerMethodField()
    published = serializers.SerializerMethodField()
    transcript_status = serializers.SerializerMethodField()
    has_document = serializers.SerializerMethodField()
    has_body = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = ["id", "kind", "title", "description", "body", "has_body", "quiz_source", "video", "source",
                  "original_filename", "file_size", "has_document", "targets", "published", "published_at",
                  "created_at", "transcript_status"]

    def get_has_document(self, obj):
        return bool(obj.document_file)

    def get_has_body(self, obj):
        return bool(obj.body.strip())

    def to_representation(self, obj):
        data = super().to_representation(obj)
        # A summary can be ~20k characters: list rows carry only `has_body`; the text comes from the
        # single-item endpoint, so a long list stays light.
        if self.context.get("list"):
            data.pop("body", None)
        return data

    def get_transcript_status(self, obj):
        row = getattr(obj, "transcript", None) if hasattr(obj, "transcript") else None
        return row.status if row else "none"

    def get_video(self, obj):
        return describe_video(obj.video_provider, obj.video_ref)

    def get_targets(self, obj):
        return {
            "grades": [{"id": g.id, "name": g.name} for g in obj.target_grades.all()],
            "groups": [{"id": g.id, "name": g.name} for g in obj.target_groups.all()],
            "students": [{"id": e.id, "name": e.display_name} for e in obj.target_enrollments.all()],
        }

    def get_published(self, obj):
        return obj.published_at is not None


class ContentItemWriteSerializer(serializers.ModelSerializer):
    """Create + PATCH. Every target id is validated against the caller's own
    environment; unknown ids are rejected (never silently dropped)."""

    video_provider = serializers.ChoiceField(choices=ContentItem._meta.get_field("video_provider").choices, required=False)
    video_ref = serializers.CharField(required=False, allow_blank=True, max_length=255)
    grade_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    group_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    enrollment_ids = serializers.ListField(child=serializers.IntegerField(), required=False, write_only=True)
    kind = serializers.ChoiceField(choices=ContentItem.Kind.choices, required=False)
    body = serializers.CharField(required=False, allow_blank=True, max_length=MAX_SUMMARY_CHARS, trim_whitespace=False)

    class Meta:
        model = ContentItem
        fields = ["id", "kind", "title", "description", "body", "quiz_source", "video_provider", "video_ref",
                  "grade_ids", "group_ids", "enrollment_ids"]
        read_only_fields = ["id"]

    def validate_title(self, value):
        value = value.strip()
        if not value:
            raise serializers.ValidationError("هذا الحقل مطلوب.")
        return value

    def _targets(self, model, ids, field):
        ids = list(dict.fromkeys(ids))
        if len(ids) > MAX_TARGETS:
            raise serializers.ValidationError({field: "عدد كبير جدًا."})
        rows = list(model.objects.filter(environment=self.context["request"].environment, id__in=ids))
        if len(rows) != len(ids):
            raise serializers.ValidationError({field: "عنصر غير موجود."})
        return rows

    def validate(self, attrs):
        # The kind is fixed when the item is created: turning a video into a PDF would leave its blob
        # and transcript orphaned and change what students were already told they received.
        current = getattr(self.instance, "kind", None)
        kind = attrs.get("kind", current or ContentItem.Kind.VIDEO)
        if current and kind != current:
            raise serializers.ValidationError({"kind": "لا يمكن تغيير نوع المحتوى بعد إنشائه."})
        attrs["kind"] = kind
        if kind != ContentItem.Kind.SUMMARY and attrs.get("body", "").strip():
            raise serializers.ValidationError({"body": "النص متاح للملخصات فقط."})
        if kind == ContentItem.Kind.VIDEO:
            provider = attrs.get("video_provider", getattr(self.instance, "video_provider", "none"))
            ref = attrs.get("video_ref", getattr(self.instance, "video_ref", ""))
            if "video_provider" in attrs and attrs["video_provider"] == "none" and "video_ref" not in attrs:
                ref = ""
            try:
                attrs["video_ref"] = validate_video(provider, ref)
            except VideoRefError as e:
                raise serializers.ValidationError({"video_ref": str(e)})
            attrs["video_provider"] = provider
        else:
            # A PDF or a summary never carries a video reference.
            attrs["video_provider"], attrs["video_ref"] = "none", ""
        if "grade_ids" in attrs:
            attrs["_grades"] = self._targets(Grade, attrs.pop("grade_ids"), "grade_ids")
        if "group_ids" in attrs:
            attrs["_groups"] = self._targets(Group, attrs.pop("group_ids"), "group_ids")
        if "enrollment_ids" in attrs:
            attrs["_enrollments"] = self._targets(Enrollment, attrs.pop("enrollment_ids"), "enrollment_ids")
        return attrs

    def _apply(self, instance, attrs):
        for key, rel in (("_grades", instance.target_grades), ("_groups", instance.target_groups), ("_enrollments", instance.target_enrollments)):
            if key in attrs:
                rel.set(attrs[key])

    def create(self, validated):
        extra = {k: validated.pop(k) for k in ("_grades", "_groups", "_enrollments") if k in validated}
        instance = super().create(validated)
        self._apply(instance, extra)
        return instance

    def update(self, instance, validated):
        extra = {k: validated.pop(k) for k in ("_grades", "_groups", "_enrollments") if k in validated}
        instance = super().update(instance, validated)
        self._apply(instance, extra)
        return instance

    def to_representation(self, instance):
        return ContentItemSerializer(instance, context=self.context).data
