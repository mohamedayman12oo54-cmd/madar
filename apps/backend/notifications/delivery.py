"""
Delivers PENDING notifications through the configured push provider. Shared by the `process_notifications`
command (cron / `--loop`) and by `notifications.dispatch` (started the moment a notification is saved), so the
two can run side by side.

Safe to run from many threads / processes at once: each row is claimed with `SELECT ... FOR UPDATE SKIP LOCKED`
inside its own transaction and re-checked as still pending, so a notification is sent to a device once, never
twice (on SQLite, which has no row locks, the same re-check applies but concurrent writers are serialised by the
database anyway).

A notification older than NOTIFICATION_MAX_AGE_HOURS is NOT pushed: "exam opens today" arriving two days late is
worse than not arriving. It is marked failed with the reason `expired`; it stays in the in-app inbox.
"""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Notification
from .providers import get_provider

EXPIRED = "انتهت صلاحية الإشعار قبل إرساله"


def deliver_pending(limit=100) -> dict:
    """-> {"sent": n, "failed": n, "expired": n}"""
    provider = get_provider()
    cutoff = timezone.now() - timedelta(hours=getattr(settings, "NOTIFICATION_MAX_AGE_HOURS", 48))
    ids = list(Notification.objects.filter(
        delivery_status=Notification.DeliveryStatus.PENDING).order_by("id").values_list("id", flat=True)[:limit])
    sent = failed = expired = 0
    for pk in ids:
        with transaction.atomic():
            n = (Notification.objects.select_for_update(skip_locked=True)
                 .filter(pk=pk, delivery_status=Notification.DeliveryStatus.PENDING).first())
            if n is None:  # another worker has it, or it was delivered since we listed it
                continue
            if n.created_at < cutoff:
                n.delivery_status = Notification.DeliveryStatus.FAILED
                n.delivery_error = EXPIRED
                expired += 1
            else:
                result = provider.send(n)
                if result.success:
                    n.delivery_status = Notification.DeliveryStatus.SENT
                    n.delivered_at = timezone.now()
                    n.delivery_error = ""
                    sent += 1
                else:
                    n.delivery_status = Notification.DeliveryStatus.FAILED
                    n.delivery_error = result.error[:255]
                    failed += 1
            n.save(update_fields=["delivery_status", "delivered_at", "delivery_error"])
    return {"sent": sent, "failed": failed, "expired": expired}
