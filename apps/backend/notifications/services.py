"""
Called from domain code (currently only scheduling/models.py) inside the
SAME transaction as the state change that triggered it — see module
docstring in models.py for why that matters. Never called from a view
directly; a view triggers a domain action (e.g. SessionInstance.open()),
and the domain action calls here.
"""
from .models import Notification

SESSION_EVENT_COPY = {
    Notification.Type.SESSION_OPENED: "الجلسة أصبحت مفتوحة الآن.",
    Notification.Type.SESSION_REOPENED: "أُعيد فتح الجلسة.",
}


def notify_session_event(session, event_type: str) -> Notification:
    """Creates a PENDING Notification for the session's group's teacher
    (the environment owner). Does not send anything — delivery is a
    separate, asynchronous step (see providers.py and
    management/commands/process_notifications.py). Reopening a session does
    NOT touch any notification already created for an earlier open/close —
    each call here creates a new, independent row (spec: reopening does not
    retroactively retract an already-fired notification)."""
    return Notification.objects.create(
        environment=session.environment,
        recipient=session.environment.owner,
        type=event_type,
        title=f"مجموعة {session.group.name}",
        body=SESSION_EVENT_COPY.get(event_type, ""),
        session=session,
    )
