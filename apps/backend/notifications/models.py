"""
Phase 5 / Notifications.

Architecture, matched deliberately to the spec's own words:

  domain event -> notification event -> async delivery

DESIGN CHOICE (flagged): the spec's task list names two things —
"notification records" and "notification events" — as if they were two
tables. This implementation uses ONE: a `Notification` row *is* the
notification event the moment it's created (`delivery_status="pending"`),
and becomes the delivered record once a worker processes it
(`delivery_status="sent"/"failed"`). A separate always-1:1 "event" table
that carries no information the Notification row doesn't already have would
only add a join, not a capability — this is the standard simplification of
the transactional-outbox pattern when the event and the resulting record
have the same shape. If a future phase needs an event that does NOT always
become one delivered notification (e.g. fan-out to many recipients from one
event), that's the point to actually split them.

Transactional guarantee: callers (e.g. scheduling.models.SessionInstance)
create a Notification inside the SAME transaction.atomic() block as the
domain state change that triggered it — see notify_session_event() in
services.py, and its call sites in scheduling/models.py. If the domain save
fails, the notification is never created; if the notification creation
somehow failed, the domain save would roll back too (both are ORM writes in
one atomic block).

Delivery is asynchronous: this app never calls a push/SMS provider from a
request/response cycle. A separate worker (management command
`process_notifications`) drains PENDING rows — see providers.py.
"""
from django.conf import settings
from django.db import models

from environments.tenancy import TenantOwnedModel


class Notification(TenantOwnedModel):
    class Type(models.TextChoices):
        SESSION_OPENED = "session_opened", "تم فتح جلسة"
        SESSION_REOPENED = "session_reopened", "تم إعادة فتح جلسة"

    class DeliveryStatus(models.TextChoices):
        PENDING = "pending", "قيد الإرسال"
        SENT = "sent", "تم الإرسال"
        FAILED = "failed", "فشل الإرسال"

    recipient = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="notifications")
    type = models.CharField(max_length=30, choices=Type.choices)
    title = models.CharField(max_length=150)
    body = models.CharField(max_length=500, blank=True)

    # Loosely tied to a session, since the only trigger this phase implements
    # is session lifecycle — nullable/SET_NULL so a note about a since-deleted
    # session doesn't disappear.
    session = models.ForeignKey(
        "scheduling.SessionInstance", on_delete=models.SET_NULL, null=True, blank=True, related_name="notifications"
    )

    delivery_status = models.CharField(max_length=10, choices=DeliveryStatus.choices, default=DeliveryStatus.PENDING)
    delivery_error = models.CharField(max_length=255, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.type} -> {self.recipient} [{self.delivery_status}]"
