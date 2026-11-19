"""
Madar Control Center — persistence for the internal team's operating tools.

Nothing here duplicates an existing model: users, environments, billing, AI operations, notifications and
guardian messages are READ from their own apps. This app only adds what did not exist:

  Role / TeamProfile      role-based access control for `team` accounts
  AuditLog                append-only record of administrative actions
  Ticket*                 the support / complaint ticketing system
  JobRun                  execution records of the background commands
  NotificationTemplate,
  PlatformNotice(+Delivery)  platform -> people notices sent by the team
  PlatformSetting         runtime-tunable operating settings
"""
import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from .permissions_catalog import PERMISSIONS


# --------------------------------------------------------------------------- RBAC
class Role(models.Model):
    key = models.SlugField(max_length=40, unique=True)
    name = models.CharField(max_length=80)
    description = models.CharField(max_length=300, blank=True)
    permissions = models.JSONField(default=list, blank=True)
    # System roles ship with Madar and cannot be deleted; super_admin cannot be edited either.
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["id"]

    def clean_permissions(self):
        return sorted({p for p in (self.permissions or []) if p in PERMISSIONS})

    def __str__(self):
        return self.name


class TeamProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="team_profile",
                                limit_choices_to={"role": "team"})
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="members")
    # Per-person adjustments on top of the role.
    extra_permissions = models.JSONField(default=list, blank=True)
    revoked_permissions = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.user} · {self.role.key}"


# --------------------------------------------------------------------------- audit
class ImmutableQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise PermissionError("Audit records cannot be modified.")

    def delete(self):
        raise PermissionError("Audit records cannot be deleted.")


class AuditLog(models.Model):
    """Who did what to which record. Append-only: the application has no code path that edits or removes a row,
    and the model refuses both (save on an existing row, delete, bulk update, bulk delete). The Django admin does
    not register it. Credentials are scrubbed before they are stored (control/audit.py)."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="+")
    actor_label = models.CharField(max_length=200, blank=True)  # survives the account being removed
    action = models.CharField(max_length=60, db_index=True)
    entity_type = models.CharField(max_length=40, db_index=True)
    entity_id = models.CharField(max_length=40, blank=True)
    entity_label = models.CharField(max_length=200, blank=True)
    before = models.JSONField(default=dict, blank=True)
    after = models.JSONField(default=dict, blank=True)
    note = models.CharField(max_length=300, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = ImmutableQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at", "-id"]

    def save(self, *args, **kwargs):
        if self.pk is not None and not self._state.adding:
            raise PermissionError("Audit records cannot be modified.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Audit records cannot be deleted.")

    def __str__(self):
        return f"{self.action} {self.entity_type}#{self.entity_id}"


# --------------------------------------------------------------------------- support
class TicketCategory(models.Model):
    name = models.CharField(max_length=80, unique=True)
    description = models.CharField(max_length=200, blank=True)
    order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order", "id"]

    def __str__(self):
        return self.name


class Ticket(models.Model):
    class Status(models.TextChoices):
        OPEN = "open", "مفتوحة"
        IN_PROGRESS = "in_progress", "قيد المعالجة"
        WAITING = "waiting_for_user", "بانتظار العميل"
        RESOLVED = "resolved", "تم الحل"
        CLOSED = "closed", "مغلقة"

    class Priority(models.TextChoices):
        LOW = "low", "منخفضة"
        MEDIUM = "medium", "متوسطة"
        HIGH = "high", "عالية"
        CRITICAL = "critical", "حرجة"

    class Kind(models.TextChoices):
        TICKET = "ticket", "تذكرة"
        COMPLAINT = "complaint", "شكوى"

    class RequesterKind(models.TextChoices):
        TEACHER = "teacher", "معلّم"
        STUDENT = "student", "طالب"
        PARENT = "parent", "ولي أمر"
        OTHER = "other", "آخر"

    class Source(models.TextChoices):
        CUSTOMER = "customer", "من العميل"
        STAFF = "staff", "من الفريق"

    ACTIVE = ("open", "in_progress", "waiting_for_user")
    # Statuses in which the clock is running on the team (waiting for the customer pauses it).
    WORKING = ("open", "in_progress")

    subject = models.CharField(max_length=200)
    description = models.TextField(max_length=5000)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.TICKET)
    category = models.ForeignKey(TicketCategory, on_delete=models.PROTECT, related_name="tickets")
    priority = models.CharField(max_length=10, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN)

    # The customer. `requester` is null for a guardian (who has no account) or when the account is later removed;
    # the snapshot fields keep the ticket readable either way.
    requester = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="support_tickets")
    requester_kind = models.CharField(max_length=10, choices=RequesterKind.choices, default=RequesterKind.OTHER)
    requester_name = models.CharField(max_length=150, blank=True)
    requester_email = models.CharField(max_length=254, blank=True)
    requester_phone = models.CharField(max_length=20, blank=True)
    environment = models.ForeignKey("environments.Environment", on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+")

    source = models.CharField(max_length=10, choices=Source.choices, default=Source.CUSTOMER)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    assignee = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                 related_name="assigned_tickets", limit_choices_to={"role": "team"})

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    last_activity_at = models.DateTimeField(default=timezone.now, db_index=True)
    # The last public message came from the customer / from the team — drives "response status".
    awaiting_team = models.BooleanField(default=True)
    due_at = models.DateTimeField(null=True, blank=True, db_index=True)
    first_response_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    reopen_count = models.PositiveIntegerField(default=0)

    rating = models.PositiveSmallIntegerField(null=True, blank=True)
    rating_comment = models.CharField(max_length=500, blank=True)
    rated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-last_activity_at", "-id"]
        indexes = [models.Index(fields=["status", "priority"]), models.Index(fields=["assignee", "status"])]
        constraints = [
            models.CheckConstraint(condition=models.Q(rating__isnull=True) | models.Q(rating__gte=1, rating__lte=5),
                                   name="ticket_rating_1_to_5"),
        ]

    @property
    def number(self):
        return f"MDR-{self.pk:06d}" if self.pk else ""

    def __str__(self):
        return f"{self.number} {self.subject}"


class TicketMessage(models.Model):
    class Kind(models.TextChoices):
        CUSTOMER = "customer", "العميل"
        AGENT = "agent", "الفريق"
        INTERNAL = "internal", "ملاحظة داخلية"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="messages")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                               related_name="+")
    author_name = models.CharField(max_length=150, blank=True)
    body = models.TextField(max_length=5000)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "id"]


def attachment_path(instance, filename):
    # The stored name is random: the client-supplied name is kept only as display text.
    ext = (filename.rsplit(".", 1)[-1] if "." in filename else "bin").lower()[:5]
    return f"tickets/{timezone.now():%Y/%m}/{uuid.uuid4().hex}.{ext}"


class TicketAttachment(models.Model):
    message = models.ForeignKey(TicketMessage, on_delete=models.CASCADE, related_name="attachments")
    file = models.FileField(upload_to=attachment_path)
    original_name = models.CharField(max_length=150)
    content_type = models.CharField(max_length=60)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)


class TicketEvent(models.Model):
    """The ticket's history. Support metrics (first response, resolution time, reopen rate, workload) are computed
    from these rows and from the timestamps on the ticket — never from stored/hardcoded numbers."""

    class Kind(models.TextChoices):
        CREATED = "created", "إنشاء"
        STATUS = "status", "تغيير الحالة"
        PRIORITY = "priority", "تغيير الأولوية"
        ASSIGNED = "assigned", "إسناد"
        CATEGORY = "category", "تغيير التصنيف"
        REPLY = "reply", "رد"
        NOTE = "note", "ملاحظة داخلية"
        CUSTOMER_REPLY = "customer_reply", "رد العميل"
        REOPENED = "reopened", "إعادة فتح"
        RATED = "rated", "تقييم"

    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="events")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                              related_name="+")
    actor_name = models.CharField(max_length=150, blank=True)
    from_value = models.CharField(max_length=80, blank=True)
    to_value = models.CharField(max_length=80, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["created_at", "id"]


# --------------------------------------------------------------------------- jobs
class JobRun(models.Model):
    """One execution of a background command (control/jobs.py writes these; the four workers wrap their loop in
    it). The System Health page reads ONLY these rows and live queue counts — never an assumed schedule."""

    class Status(models.TextChoices):
        OK = "ok", "نجحت"
        FAILED = "failed", "فشلت"

    name = models.CharField(max_length=60, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices)
    started_at = models.DateTimeField(db_index=True)
    finished_at = models.DateTimeField()
    duration_ms = models.PositiveIntegerField(default=0)
    processed = models.PositiveIntegerField(default=0)
    failed_items = models.PositiveIntegerField(default=0)
    error = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering = ["-started_at", "-id"]
        indexes = [models.Index(fields=["name", "-started_at"])]


# --------------------------------------------------------------------------- notifications
class NotificationTemplate(models.Model):
    name = models.CharField(max_length=80, unique=True)
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=300, blank=True)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]


class PlatformNotice(models.Model):
    """A message from Madar to people (Web Push to every device they enabled). Distinct from a teacher's
    `notifications.Notification`, which belongs to one environment and is addressed to a student."""

    class Audience(models.TextChoices):
        USER = "user", "مستخدم محدد"
        USERS = "users", "مستخدمون محددون"
        TEACHERS = "teachers", "كل المعلّمين"
        STUDENTS = "students", "كل الطلاب"
        ENVIRONMENT = "environment", "بيئة محددة"

    title = models.CharField(max_length=150)
    body = models.CharField(max_length=300, blank=True)
    url = models.CharField(max_length=200, blank=True, default="/")
    audience = models.CharField(max_length=12, choices=Audience.choices)
    environment = models.ForeignKey("environments.Environment", on_delete=models.SET_NULL, null=True, blank=True,
                                    related_name="+")
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="+")
    recipient_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]


class PlatformNoticeDelivery(models.Model):
    class Status(models.TextChoices):
        QUEUED = "queued", "في الانتظار"        # accepted, not yet handed to the push service
        SENT = "sent", "سُلّم لخدمة الدفع"       # the push service accepted it (NOT proof the device showed it)
        FAILED = "failed", "فشل"
        NO_DEVICE = "no_device", "لا يوجد جهاز مفعّل"

    notice = models.ForeignKey(PlatformNotice, on_delete=models.CASCADE, related_name="deliveries")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="+")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED, db_index=True)
    devices_sent = models.PositiveSmallIntegerField(default=0)
    devices_failed = models.PositiveSmallIntegerField(default=0)
    attempted_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["notice", "user"], name="one_delivery_per_user_per_notice")]


# --------------------------------------------------------------------------- settings
class PlatformSetting(models.Model):
    key = models.CharField(max_length=60, primary_key=True)
    value = models.JSONField()
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                   related_name="+")
    updated_at = models.DateTimeField(auto_now=True)
