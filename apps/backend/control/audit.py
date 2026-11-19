"""Writing the audit trail. `record()` is the only writer, and it removes anything that looks like a credential
before the row is stored."""
import re

from .models import AuditLog

_SECRET = re.compile(r"pass(word)?|token|secret|otp|card|cvv|authorization|signature|api[_-]?key|private", re.I)
MAX_VALUE = 300


def scrub(value, depth=0):
    if isinstance(value, dict):
        return {str(k)[:60]: ("***" if _SECRET.search(str(k)) else scrub(v, depth + 1))
                for k, v in list(value.items())[:40]}
    if isinstance(value, (list, tuple)):
        return [scrub(v, depth + 1) for v in list(value)[:40]] if depth < 3 else []
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:MAX_VALUE]


def client_ip(request):
    """The caller's address by the SAME rule the rate limiters use (DRF `get_ident`, which honours
    REST_FRAMEWORK["NUM_PROXIES"]): behind a trusted proxy that is the forwarded client, never a spoofable header."""
    if request is None:
        return None
    from rest_framework.throttling import BaseThrottle

    return BaseThrottle().get_ident(request) or None


def record(request, action, entity_type, entity_id="", label="", before=None, after=None, note="", actor=None):
    if actor is None and request is not None and getattr(request.user, "is_authenticated", False):
        actor = request.user
    return AuditLog.objects.create(
        actor=actor if getattr(actor, "pk", None) else None,
        actor_label=((getattr(actor, "name", "") or getattr(actor, "username", "") or "")[:200]) if actor else "",
        action=action[:60], entity_type=entity_type[:40], entity_id=str(entity_id)[:40], entity_label=str(label)[:200],
        before=scrub(before or {}), after=scrub(after or {}), note=str(note)[:300],
        ip_address=client_ip(request),
        user_agent=(request.META.get("HTTP_USER_AGENT", "")[:200] if request is not None else ""),
    )


def diff(old: dict, new: dict):
    """(before, after) holding only the keys whose value changed."""
    keys = [k for k in new if old.get(k) != new.get(k)]
    return {k: old.get(k) for k in keys}, {k: new.get(k) for k in keys}


def record_view(request, entity_type, entity_id, label=""):
    """Reading private records across environments is itself an auditable act. The same person opening the same
    record again within ten minutes is logged once, so browsing does not bury the real changes."""
    from datetime import timedelta

    from django.utils import timezone

    actor = request.user
    since = timezone.now() - timedelta(minutes=10)
    if AuditLog.objects.filter(actor_id=actor.pk, action="view", entity_type=entity_type[:40],
                               entity_id=str(entity_id)[:40], created_at__gte=since).exists():
        return None
    return record(request, "view", entity_type, entity_id, label)
