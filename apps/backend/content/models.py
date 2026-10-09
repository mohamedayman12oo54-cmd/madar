"""
Phase 5 / Content.

A ContentItem is a piece of educational material a teacher keeps in their
environment, optionally tied to one Grade (or general, if `grade` is null).
The optional video is stored as (provider, opaque ref) only — never a URL —
and turned into an embeddable form solely by content/video.py, so no
provider is ever referenced from domain code (spec: internal Video
abstraction).

No file/attachment upload is implemented: the spec's upload-security
checklist applies "if the application accepts" uploads, and nothing in the
Phase 5 requirements calls for accepting any — keeping it out keeps the
attack surface (path traversal, malicious types, storage) at zero rather
than half-built.
"""
from django.core.exceptions import ValidationError
from django.db import models

from academics.models import Grade
from environments.tenancy import TenantOwnedModel

from .video import PROVIDER_CHOICES


class ContentItem(TenantOwnedModel):
    grade = models.ForeignKey(Grade, on_delete=models.SET_NULL, null=True, blank=True, related_name="content_items")
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    video_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default="none")
    video_ref = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        if self.grade_id and self.environment_id and self.grade.environment_id != self.environment_id:
            raise ValidationError("المحتوى يجب أن ينتمي لنفس بيئة الصف.")

    def __str__(self):
        return self.title
