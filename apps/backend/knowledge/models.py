"""
The central, product-owned Knowledge Base (docs: `00-overview/glossary.md`,
`09-operations/knowledge-base.md`, `01-product/scope.md`).

Deliberately NOT a TenantOwnedModel. The KB is *central and curated by the
Content Maintainer* — it belongs to Madar, not to any Teacher Environment.
Teachers do not curate AI sources in V1, so there is no `environment` column
here and no teacher-facing write path anywhere in this app.

Lifecycle is the documented one and nothing more: draft -> published, with a
lightweight integer version. Only PUBLISHED documents are authoritative for AI
consumption (`published` manager), which is what gives the Study Assistant its
bounded source contract.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone


class PublishedKBManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=KBDocument.Status.PUBLISHED)


class KBDocument(models.Model):
    class Status(models.TextChoices):
        DRAFT = "draft", "مسودة"
        PUBLISHED = "published", "منشورة"

    title = models.CharField(max_length=200)
    body = models.TextField()
    # Free-text subject/topic label used to narrow retrieval. Not a taxonomy:
    # V1 explicitly does not require a content-publishing platform.
    topic = models.CharField(max_length=120, blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    version = models.PositiveIntegerField(default=1)
    published_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="kb_documents", limit_choices_to={"role": "team"},
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    published = PublishedKBManager()

    class Meta:
        ordering = ["-updated_at"]
        indexes = [models.Index(fields=["status"])]

    def publish(self):
        """draft -> published. Re-publishing an edited document bumps the
        lightweight version so AI answers can cite exactly what they used."""
        if self.status == self.Status.PUBLISHED:
            self.version += 1
        self.status = self.Status.PUBLISHED
        self.published_at = timezone.now()
        self.save(update_fields=["status", "version", "published_at", "updated_at"])
        return self

    def unpublish(self):
        """Withdraw from AI consumption without deleting the curation work."""
        self.status = self.Status.DRAFT
        self.save(update_fields=["status", "updated_at"])
        return self

    def __str__(self):
        return f"{self.title} (v{self.version}, {self.status})"
