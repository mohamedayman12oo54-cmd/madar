"""
Notifications — the documented event catalog (functional.md / PD-4):
absent (auto), not_studied (auto), new_video, rating_published, broadcast, plus the two content
events that used to be mislabelled as "new video": new_exam (an exam was published or re-opened for a
student) and new_material (a PDF or a written summary was published).
There is no "session opened" or "new quiz" notification.

A Notification row IS the event the moment it is created (delivery_status
"pending") and becomes the delivered record once the worker handles it.
The recipient is the STUDENT's account row — it exists even before the
student claims it, so a notification fired while unclaimed is simply waiting
in their in-app inbox after they claim (docs: in-app + push channels only).

Created inside the SAME transaction as the domain fact that caused it
(ADR-005): attendance/recitation mark, video publish, rating publish,
broadcast. Delivery is asynchronous (management command
`process_notifications`) and can fail without touching the domain record.
Fired notifications are never retracted by later corrections.
"""
from django.conf import settings
from django.db import models

from environments.tenancy import TenantOwnedModel


class Notification(TenantOwnedModel):
    class Type(models.TextChoices):
        ABSENT = "absent", "غياب"
        NOT_STUDIED = "not_studied", "لم يذاكر"
        NEW_VIDEO = "new_video", "فيديو جديد"
        NEW_EXAM = "new_exam", "امتحان جديد"
        NEW_MATERIAL = "new_material", "ملف أو ملخص جديد"
        RATING_PUBLISHED = "rating_published", "نشر التقييم الشهري"
        BROADCAST = "broadcast", "رسالة من المعلّم"
        # Legacy values kept readable for rows created before the catalog was
        # aligned to the documentation; nothing creates them any more.
        SESSION_OPENED = "session_opened", "تم فتح جلسة (قديم)"
        SESSION_REOPENED = "session_reopened", "تم إعادة فتح جلسة (قديم)"

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "قيد الإرسال"
        SENT = "sent", "تم الإرسال"
        FAILED = "failed", "فشل الإرسال"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    enrollment = models.ForeignKey(
        "academics.Enrollment", on_delete=models.CASCADE, null=True, blank=True, related_name="notifications"
    )
    # Set for BROADCAST rows: the single message this delivery belongs to, so
    # the teacher's log can collapse N deliveries into one entry and the
    # student can open the full message.
    broadcast = models.ForeignKey("notifications.Broadcast", on_delete=models.SET_NULL,
                                  null=True, blank=True, related_name="deliveries")
    # Set for NEW_VIDEO rows: the single published video this delivery belongs
    # to, so the teacher's log shows ONE line per video instead of one per
    # student (same idea as `broadcast`).
    content_item = models.ForeignKey("content.ContentItem", on_delete=models.SET_NULL,
                                     null=True, blank=True, related_name="notifications")
    # Set for NEW_EXAM rows: the exam this delivery belongs to (the log collapses to ONE line per exam and
    # the student's "details" / push tap opens it directly).
    exam = models.ForeignKey("learning.Exam", on_delete=models.SET_NULL,
                             null=True, blank=True, related_name="notifications")
    type = models.CharField(max_length=30, choices=Type.choices)
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=500, blank=True)
    session = models.ForeignKey(
        "scheduling.SessionInstance", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications"
    )

    delivery_status = models.CharField(max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)
    delivery_error = models.CharField(max_length=255, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["environment", "-created_at"])]

    def __str__(self):
        return f"{self.type} -> {self.recipient_id} [{self.delivery_status}]"

    def target(self):
        """Where this notification points inside the student app: {"kind", "id"} or None. Used by the
        in-app "open" button and as the tap target of the push notification."""
        if self.exam_id:
            return {"kind": "exam", "id": self.exam_id}
        if self.content_item_id:
            kind = "video" if self.content_item.kind == "video" else "material"
            return {"kind": kind, "id": self.content_item_id}
        return None

    def student_path(self):
        t = self.target()
        if not t:
            return "/learn/notifications"
        return {"exam": "/learn/exams/", "video": "/learn/videos/", "material": "/learn/materials/"}[t["kind"]] + str(t["id"])


class Broadcast(TenantOwnedModel):
    """One teacher message, recorded ONCE.

    The per-student notifications are the delivery; this is the message. The
    teacher's log shows one row per broadcast (with who it went to) instead of
    one row per recipient, which previously made a message to 40 students look
    like 40 separate messages.
    """

    title = models.CharField(max_length=150)
    body = models.TextField(max_length=500, blank=True)
    grades = models.ManyToManyField("academics.Grade", blank=True, related_name="broadcasts")
    groups = models.ManyToManyField("academics.Group", blank=True, related_name="broadcasts")
    recipient_count = models.PositiveIntegerField(default=0)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.title} -> {self.recipient_count}"


class PushSubscription(models.Model):
    """One browser/device that agreed to receive Web Push for ONE user. Not tenant-scoped on purpose: a
    notification is addressed to a person (a teacher account or a student account), and the device
    belongs to whoever is signed in on it right now — so subscribing again from the same browser with a
    different account MOVES the subscription to that account (the previous owner stops receiving)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="push_subscriptions")
    endpoint = models.CharField(max_length=700, unique=True)
    p256dh = models.CharField(max_length=200)
    auth = models.CharField(max_length=100)
    user_agent = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_success_at = models.DateTimeField(null=True, blank=True)

    def info(self):
        return {"endpoint": self.endpoint, "keys": {"p256dh": self.p256dh, "auth": self.auth}}
