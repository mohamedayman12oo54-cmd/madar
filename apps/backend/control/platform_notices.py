"""Platform → people notices ("from Madar"), delivered by Web Push through the existing notifications.webpush
module. A delivery is only ever marked SENT when the push service accepted the message for at least one device —
that is the strongest signal Web Push gives; it does NOT prove the device displayed it, and the Control Center
says so. Accounts with no subscribed device are recorded as NO_DEVICE, not as a success."""
from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from academics.models import Enrollment
from accounts.models import User
from environments.models import Environment
from notifications import webpush

from .models import PlatformNotice, PlatformNoticeDelivery

MAX_RECIPIENTS = 2000
INLINE_LIMIT = 100


def valid_url(url):
    """Only an in-app path: no scheme, no protocol-relative `//host`, no backslash tricks."""
    return bool(url) and url.startswith("/") and not url.startswith("//") and "\\" not in url and len(url) <= 200 \
        and ":" not in url.split("?")[0]


def recipients_for(audience, user_ids=None, environment=None):
    base = User.objects.filter(is_active=True, is_verified=True).exclude(role="team")
    if audience in ("user", "users"):
        return base.filter(pk__in=user_ids or [])
    if audience == "teachers":
        return base.filter(role="teacher")
    if audience == "students":
        return base.filter(role="student")
    if audience == "environment":
        student_ids = Enrollment.objects.filter(environment=environment, is_active=True).values_list("student_id", flat=True)
        return base.filter(Q(pk=environment.owner_id) | Q(pk__in=student_ids))
    return base.none()


def create_notice(*, sender, title, body, url, audience, user_ids=None, environment=None):
    users = list(recipients_for(audience, user_ids, environment).values_list("pk", flat=True)[: MAX_RECIPIENTS + 1])
    if not users:
        return None, "no_recipients"
    if len(users) > MAX_RECIPIENTS:
        return None, "too_many"
    with transaction.atomic():
        notice = PlatformNotice.objects.create(title=title, body=body, url=url or "/", audience=audience,
                                               environment=environment, sent_by=sender, recipient_count=len(users))
        PlatformNoticeDelivery.objects.bulk_create(
            [PlatformNoticeDelivery(notice=notice, user_id=uid) for uid in users])
    return notice, None


def deliver_queued(limit=INLINE_LIMIT, notice=None) -> dict:
    """Push to queued deliveries. Each row is claimed with a conditional UPDATE first, so two workers (or the
    request and the command) never send the same notice to the same person twice."""
    counts = {"sent": 0, "failed": 0, "no_device": 0}
    qs = PlatformNoticeDelivery.objects.filter(status=PlatformNoticeDelivery.Status.QUEUED).select_related("notice")
    if notice is not None:
        qs = qs.filter(notice=notice)
    for d in list(qs.order_by("id")[:limit]):
        claimed = PlatformNoticeDelivery.objects.filter(pk=d.pk, status=PlatformNoticeDelivery.Status.QUEUED).update(
            status=PlatformNoticeDelivery.Status.FAILED, attempted_at=timezone.now())  # provisional: a crash = "failed"
        if not claimed:
            continue
        r = webpush.send_to_user(d.user_id, d.notice.title, d.notice.body, d.notice.url, tag="platform")
        if r["sent"]:
            status, key = PlatformNoticeDelivery.Status.SENT, "sent"
        elif r["failed"]:
            status, key = PlatformNoticeDelivery.Status.FAILED, "failed"
        else:
            status, key = PlatformNoticeDelivery.Status.NO_DEVICE, "no_device"
        PlatformNoticeDelivery.objects.filter(pk=d.pk).update(status=status, devices_sent=r["sent"], devices_failed=r["failed"])
        counts[key] += 1
    return counts


def notice_counts(notice):
    rows = dict(notice.deliveries.values_list("status").annotate(n=Count("id")))
    return {s: rows.get(s, 0) for s in ("queued", "sent", "failed", "no_device")}
