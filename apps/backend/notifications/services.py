"""
The only place notifications are created. Always called by domain code INSIDE
the same transaction.atomic() block as the domain change (ADR-005), never
from a view directly and never talking to a provider.
"""
from .models import Notification

T = Notification.Type


def _fmt_session(session):
    from django.utils import timezone

    return timezone.localtime(session.scheduled_at).strftime("%Y-%m-%d")


def notify_enrollment(enrollment, type_, title, body="", session=None):
    return Notification.objects.create(
        environment_id=enrollment.environment_id, recipient_id=enrollment.student_id,
        enrollment=enrollment, type=type_, title=title[:150], body=body[:500], session=session,
    )


def notify_many(enrollments, type_, title, body=""):
    """Fan out ONE event to many students (video / broadcast). Active
    enrollments only, de-duplicated by enrollment id."""
    seen, rows = set(), []
    for e in enrollments:
        if e.id in seen or not e.is_active:
            continue
        seen.add(e.id)
        rows.append(Notification(
            environment_id=e.environment_id, recipient_id=e.student_id, enrollment=e,
            type=type_, title=title[:150], body=body[:500],
        ))
    return Notification.objects.bulk_create(rows)


def notify_absent(enrollment, session):
    return notify_enrollment(
        enrollment, T.ABSENT, "تم تسجيل غيابك",
        f"سُجّل غيابك في حصة مجموعة {session.group.name} بتاريخ {_fmt_session(session)}.", session,
    )


def notify_not_studied(enrollment, session):
    return notify_enrollment(
        enrollment, T.NOT_STUDIED, "لم تذاكر الدرس",
        f"سُجّل أنك لم تذاكر الدرس في حصة مجموعة {session.group.name} بتاريخ {_fmt_session(session)}.", session,
    )
