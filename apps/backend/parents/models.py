from django.conf import settings
from django.db import models

from environments.tenancy import TenantOwnedModel


class GuardianMessage(TenantOwnedModel):
    """A message from the teacher to ONE child's guardian (a warning about absence, unpaid fees, weak exams...).

    It is addressed to an enrollment, never to a person: a guardian has no account, so they read it in the
    portal session bound to that enrollment. It is deliberately NOT a Notification — those are addressed to the
    student, and a warning about the child must not land in the child's own inbox.

    The portal is read-only with ONE exception: the guardian opening a message stamps its `read_at` (see
    GuardianMessageReadView), so the teacher can tell a warning was seen."""

    class Kind(models.TextChoices):
        WARNING = "warning", "تحذير"
        NOTE = "note", "ملاحظة"

    enrollment = models.ForeignKey("academics.Enrollment", on_delete=models.CASCADE, related_name="guardian_messages")
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.NOTE)
    title = models.CharField(max_length=150)
    body = models.TextField(max_length=1000)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
                                null=True, blank=True, related_name="+")
    # Set only for messages the system wrote itself (guardian_alerts.py): "absent:2026-11", "exam:12". One per
    # (enrollment, key), so running the worker again never repeats a warning.
    auto_key = models.CharField(max_length=40, blank=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["enrollment", "-created_at"])]
        constraints = [
            models.UniqueConstraint(fields=["enrollment", "auto_key"], condition=~models.Q(auto_key=""),
                                    name="guardian_message_one_per_auto_key"),
        ]

    @property
    def automatic(self):
        return bool(self.auto_key)

    def __str__(self):
        return f"{self.kind} -> enrollment {self.enrollment_id}"


MAX_REPLIES_PER_MESSAGE = 3


class GuardianReply(TenantOwnedModel):
    """A guardian's short answer to a teacher's message. The only free text a guardian can write, so it is
    bounded three ways: its length, the number per message, and a per-child hourly rate."""

    message = models.ForeignKey(GuardianMessage, on_delete=models.CASCADE, related_name="replies")
    enrollment = models.ForeignKey("academics.Enrollment", on_delete=models.CASCADE, related_name="guardian_replies")
    body = models.CharField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)  # when the TEACHER opened it

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [models.Index(fields=["enrollment", "read_at"])]


class GuardianAlertSettings(models.Model):
    """A teacher's choice about automatic warnings to guardians. OFF until the teacher turns it on: a parent
    must never be warned by a rule the teacher did not knowingly adopt. A threshold of 0 switches that single
    warning off."""

    environment = models.OneToOneField("environments.Environment", on_delete=models.CASCADE,
                                       related_name="guardian_alert_settings")
    enabled = models.BooleanField(default=False)
    # Absences in the current calendar month at which the guardian is warned.
    absence_threshold = models.PositiveSmallIntegerField(default=3)
    # Warn when the child's best score in an exam is below this percent.
    exam_percent_below = models.PositiveSmallIntegerField(default=50)
    # Warn from this day of the month if the month's fee is still unpaid.
    unpaid_after_day = models.PositiveSmallIntegerField(default=10)
    # Show the guardian where the child stands among classmates (by exam average). Off unless the teacher
    # wants it: a ranking is the teacher's call to publish, not the system's.
    show_rank = models.BooleanField(default=False)
