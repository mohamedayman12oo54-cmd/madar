"""
Video & content (docs: upload -> target -> watch). A ContentItem keeps ONLY
metadata + targeting + an external reference (provider + opaque id — never a
URL, never a file: the video binary lives in external storage). Targets are
any mix of whole GRADES, GROUPS and individual STUDENTS (enrollments); an item
with no target is a private draft nobody can see. PUBLISHING is the explicit
step that fires the "new video available" notification, once.
"""
from django.core.exceptions import ValidationError
import uuid

from django.conf import settings
from django.db import models
from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.utils import timezone

from academics.models import Enrollment, Grade, Group
from environments.tenancy import TenantOwnedModel

from .uploads import rendition_path, storage_path
from .video import PROVIDER_CHOICES


class ContentItem(TenantOwnedModel):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    # EITHER an external reference (provider + opaque id) OR an uploaded file.
    # `source` says which one is authoritative for playback.
    video_provider = models.CharField(max_length=20, choices=PROVIDER_CHOICES, default="none")
    video_ref = models.CharField(max_length=255, blank=True)

    class Source(models.TextChoices):
        EXTERNAL = "external", "رابط خارجي"
        UPLOAD = "upload", "ملف مرفوع"

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.EXTERNAL)

    class Processing(models.TextChoices):
        """Where a video is in the pipeline. A file is NOT playable the moment
        the bytes land: validation (and, with a transcoding provider, encoding)
        happen first, so the UI can show honest progress instead of a broken
        player."""
        NONE = "none", "لا يوجد"
        UPLOADING = "uploading", "جارٍ الرفع"
        PROCESSING = "processing", "جارٍ المعالجة"
        READY = "ready", "جاهز"
        FAILED = "failed", "فشل"

    processing_status = models.CharField(max_length=12, choices=Processing.choices, default=Processing.NONE)
    processing_error = models.TextField(blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    # Opaque handle at the streaming provider (Cloudflare Stream / Mux / ...).
    # Empty while Madar serves the bytes itself.
    playback_id = models.CharField(max_length=200, blank=True)
    # One id that ties upload -> processing -> playback -> logs together, so a
    # failure report can be traced end to end.
    trace_id = models.CharField(max_length=32, blank=True, db_index=True)
    # Stored under MEDIA_ROOT, which is NOT web-served: bytes only ever leave
    # through content.streaming after an authorisation check.
    video_file = models.FileField(upload_to=storage_path, blank=True, null=True, max_length=255)
    original_filename = models.CharField(max_length=120, blank=True)
    file_size = models.PositiveBigIntegerField(null=True, blank=True)
    content_type = models.CharField(max_length=80, blank=True)
    # Teacher-provided text the AI Quiz is generated from (summary / transcript
    # of the lesson). The video itself is an external blob the quiz cannot read.
    quiz_source = models.TextField(blank=True, max_length=4000)
    target_grades = models.ManyToManyField(Grade, blank=True, related_name="content_items")
    target_groups = models.ManyToManyField(Group, blank=True, related_name="content_items")
    target_enrollments = models.ManyToManyField(Enrollment, blank=True, related_name="content_items")
    published_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        pass

    def audience(self):
        """ACTIVE enrollments who may watch this item.

        Grade and group are a NARROWING, not a union (same rule as broadcasts):
        grade + group = students in that grade AND that group; a grade alone =
        the whole grade; a group alone = that group. Individually picked
        students are explicit additions on top. Nobody else ever qualifies.
        """
        from django.db.models import Q

        base = Enrollment.objects.filter(environment_id=self.environment_id, is_active=True)
        grade_ids = list(self.target_grades.values_list("pk", flat=True))
        group_ids = list(self.target_groups.values_list("pk", flat=True))
        direct_ids = list(self.target_enrollments.values_list("pk", flat=True))

        cond = Q(pk__in=direct_ids)
        if grade_ids or group_ids:
            narrowed = base
            if grade_ids:
                narrowed = narrowed.filter(grade_id__in=grade_ids)
            if group_ids:
                narrowed = narrowed.filter(groups__id__in=group_ids)
            cond |= Q(pk__in=narrowed.values("pk"))
        return base.filter(cond).distinct()

    @classmethod
    def visible_to(cls, enrollment):
        """Published items this ONE student may watch - the student-side mirror
        of `audience()`, so the two can never disagree."""
        from django.db.models import Exists, OuterRef, Q

        Grades, Groups, Direct = (cls.target_grades.through, cls.target_groups.through,
                                  cls.target_enrollments.through)
        has_grades = Exists(Grades.objects.filter(contentitem_id=OuterRef("pk")))
        has_groups = Exists(Groups.objects.filter(contentitem_id=OuterRef("pk")))
        grade_hit = Exists(Grades.objects.filter(contentitem_id=OuterRef("pk"), grade_id=enrollment.grade_id))
        group_hit = Exists(Groups.objects.filter(
            contentitem_id=OuterRef("pk"), group_id__in=[g.pk for g in enrollment.groups.all()]))
        direct_hit = Exists(Direct.objects.filter(contentitem_id=OuterRef("pk"), enrollment_id=enrollment.pk))
        narrowed = (Q(has_grades=True) | Q(has_groups=True)) & (Q(has_grades=False) | Q(grade_hit=True)) \
            & (Q(has_groups=False) | Q(group_hit=True))
        return (cls.objects
                .filter(environment_id=enrollment.environment_id, published_at__isnull=False)
                .annotate(has_grades=has_grades, has_groups=has_groups,
                          grade_hit=grade_hit, group_hit=group_hit, direct_hit=direct_hit)
                .filter(narrowed | Q(direct_hit=True)))

    def has_targets(self):
        return self.target_grades.exists() or self.target_groups.exists() or self.target_enrollments.exists()

    def __str__(self):
        return self.title


class VideoRendition(models.Model):
    """One server-generated, lower-resolution copy of an uploaded video.

    Created by `content.transcode` (ffmpeg). Stored privately exactly like the
    original: no public URL, random name, and reachable only through a signed
    ticket that names the height. Tenancy comes from the parent item, whose
    environment every access path re-checks.
    """
    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="renditions")
    height = models.PositiveSmallIntegerField()
    video_file = models.FileField(upload_to=rendition_path, max_length=255)
    file_size = models.PositiveBigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["item", "height"], name="uniq_rendition_per_item_height")]
        ordering = ["-height"]

    @property
    def label(self):
        return f"{self.height}p"


@receiver(post_delete, sender=VideoRendition)
def _delete_rendition_blob(sender, instance, **kwargs):
    """Rows vanish by CASCADE when an item is deleted; the blob must go too."""
    if instance.video_file:
        instance.video_file.storage.delete(instance.video_file.name)


class VideoProgress(TenantOwnedModel):
    """Per-student viewing activity for one item.

    Feeds the teacher's view of engagement and is an input the monthly
    evaluation can use. Written only by the owning student, for themselves.
    """
    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="progress")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.CASCADE, related_name="video_progress")
    position_seconds = models.PositiveIntegerField(default=0)
    duration_seconds = models.PositiveIntegerField(default=0)
    percent = models.PositiveSmallIntegerField(default=0)
    completed = models.BooleanField(default=False)
    started_at = models.DateTimeField(auto_now_add=True)
    last_watched_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["item", "enrollment"], name="uniq_progress_per_item_enrollment"),
        ]
        ordering = ["-last_watched_at"]

    def apply(self, position, duration):
        """Progress only moves forward: a seek back to 0 must not erase that
        the student already watched the lesson."""
        position = max(0, int(position or 0))
        duration = max(0, int(duration or 0))
        if duration:
            self.duration_seconds = duration
            position = min(position, duration)
        self.position_seconds = position
        if self.duration_seconds:
            pct = round(position * 100 / self.duration_seconds)
            self.percent = max(self.percent, min(100, pct))
            if self.percent >= 95:
                self.completed = True
        return self

    def __str__(self):
        return f"{self.enrollment} · {self.item} · {self.percent}%"


class UploadSession(TenantOwnedModel):
    """A resumable upload (TUS-style).

    Large videos and flaky connections do not mix: without this, a 95%-complete
    upload that drops has to start from zero. The session records how many
    bytes have landed (`offset`), so the client asks "where was I?" (HEAD) and
    continues from exactly there (PATCH).

    The session is the authorisation too: it is created only after the server
    has checked who the teacher is and what they may upload, and it carries the
    declared size and type so limits are enforced before any byte is written —
    not after a 10 GB file has already been accepted.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "جارٍ الرفع"
        COMPLETED = "completed", "اكتمل"
        ABORTED = "aborted", "أُلغي"
        EXPIRED = "expired", "انتهت صلاحيته"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(ContentItem, on_delete=models.CASCADE, related_name="upload_sessions")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    filename = models.CharField(max_length=120)
    content_type = models.CharField(max_length=80, blank=True)
    total_bytes = models.PositiveBigIntegerField()
    offset = models.PositiveBigIntegerField(default=0)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.ACTIVE)
    storage_path = models.CharField(max_length=255, blank=True)
    error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    expires_at = models.DateTimeField()

    class Meta:
        ordering = ["-created_at"]

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_complete(self):
        return self.offset >= self.total_bytes

    @property
    def remaining(self):
        return max(0, self.total_bytes - self.offset)

    def __str__(self):
        return f"upload {self.id} ({self.offset}/{self.total_bytes})"


class Transcript(TenantOwnedModel):
    """Speech-to-text of an uploaded lesson video (pipeline step 2).

    One row per item: re-uploading the video resets it and transcribes again.
    The text lives HERE, in Madar's own database, so later steps (validation,
    quiz generation) never depend on the transcriber. `segments` keeps the
    timestamps ([{"start","end","text"}], seconds) so a question can later
    point at the exact moment of the lesson that supports it.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "قيد الانتظار"
        PROCESSING = "processing", "جارٍ التحويل"
        COMPLETED = "completed", "مكتمل"
        FAILED = "failed", "فشل"

    item = models.OneToOneField(ContentItem, on_delete=models.CASCADE, related_name="transcript")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING)
    language = models.CharField(max_length=16, blank=True)
    text = models.TextField(blank=True)
    segments = models.JSONField(default=list, blank=True)
    duration_seconds = models.PositiveIntegerField(null=True, blank=True)
    provider = models.CharField(max_length=40, blank=True)
    error = models.TextField(blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"transcript of #{self.item_id} [{self.status}]"
