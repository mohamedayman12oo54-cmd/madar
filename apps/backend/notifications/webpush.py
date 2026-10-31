"""
Web Push delivery (RFC 8030 / 8291 / VAPID 8292).

How a message reaches a closed app: the browser gave us a subscription (an endpoint on Google's / Apple's
/ Mozilla's push service plus encryption keys). We encrypt the payload for that device, sign it with our
VAPID key and POST it to the endpoint; the push service wakes the device's service worker (public/sw.js),
which shows the notification. No Firebase account and no per-message cost.
"""
import json
import logging

from django.conf import settings
from django.utils import timezone

from .models import PushSubscription
from .providers import DeliveryResult, PushProvider

log = logging.getLogger(__name__)

TTL_SECONDS = 24 * 60 * 60  # keep trying for a day if the phone is off
GONE = {404, 410}  # the push service says this subscription no longer exists


def enabled() -> bool:
    return bool(settings.VAPID_PUBLIC_KEY and settings.VAPID_PRIVATE_KEY)


def _send_one(sub: PushSubscription, payload: str):
    """-> (ok, gone, error). Network/vendor details stay inside this function (and are patched in tests)."""
    from pywebpush import WebPushException, webpush

    try:
        webpush(
            subscription_info=sub.info(), data=payload, ttl=TTL_SECONDS, timeout=10,
            vapid_private_key=settings.VAPID_PRIVATE_KEY,
            vapid_claims={"sub": settings.VAPID_CONTACT},
        )
        return True, False, ""
    except WebPushException as e:
        status = getattr(getattr(e, "response", None), "status_code", None)
        return False, status in GONE, f"push {status or 'error'}"
    except Exception as e:  # network down, bad key, ...
        return False, False, type(e).__name__


def send_to_user(user_id: int, title: str, body: str = "", url: str = "/", tag: str = "") -> dict:
    """Push to every device of one user. Dead subscriptions are removed. Returns counts."""
    payload = json.dumps({"title": title[:150], "body": body[:300], "url": url, "tag": tag}, ensure_ascii=False)
    sent = failed = removed = 0
    for sub in PushSubscription.objects.filter(user_id=user_id):
        ok, gone, _err = _send_one(sub, payload)
        if ok:
            sent += 1
            PushSubscription.objects.filter(pk=sub.pk).update(last_success_at=timezone.now())
        elif gone:
            sub.delete()
            removed += 1
        else:
            failed += 1
    return {"sent": sent, "failed": failed, "removed": removed}


class WebPushProvider(PushProvider):
    """Plugs into the existing worker (`process_notifications`): a Notification row is delivered to its
    recipient's devices. A recipient with no subscribed device is NOT a failure — the in-app inbox still
    has the message — only a device we could not reach is."""

    def send(self, notification) -> DeliveryResult:
        url = notification.student_path()  # an exam / material / video opens directly; the rest the inbox
        r = send_to_user(notification.recipient_id, notification.title, notification.body, url,
                         tag=f"n{notification.pk}")
        if r["failed"] and not r["sent"]:
            return DeliveryResult(success=False, error="تعذّر الوصول إلى جهاز المستلم")
        return DeliveryResult(success=True)
