"""The ticket lifecycle in one place. Every status / priority / assignment / message change — from the team's
endpoints, the customers' endpoints and the bulk action — goes through these functions, so the rules, the history
rows and the audit trail cannot drift apart.

Lifecycle (docs: Control Center, Support):
    open ⇄ in_progress ⇄ waiting_for_user → resolved → closed        resolved / closed → open|in_progress = reopen
The team's clock (resolution deadline) runs only while a ticket is open / in progress."""
from datetime import timedelta

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import PermissionDenied, ValidationError

from . import audit
from .models import Ticket, TicketAttachment, TicketCategory, TicketEvent, TicketMessage
from .settings_registry import get_setting

S = Ticket.Status
TRANSITIONS = {
    S.OPEN: {S.IN_PROGRESS, S.WAITING, S.RESOLVED, S.CLOSED},
    S.IN_PROGRESS: {S.OPEN, S.WAITING, S.RESOLVED, S.CLOSED},
    S.WAITING: {S.OPEN, S.IN_PROGRESS, S.RESOLVED, S.CLOSED},
    S.RESOLVED: {S.CLOSED, S.OPEN, S.IN_PROGRESS},
    S.CLOSED: {S.OPEN},
}
# Moving to one of these (or out of resolved/closed) needs `tickets.resolve`; the other moves need `tickets.reply`.
NEEDS_RESOLVE = {S.RESOLVED, S.CLOSED}
REOPEN_FROM = {S.RESOLVED, S.CLOSED}

MAX_FILES = 3
MAX_FILE_BYTES = 5 * 1024 * 1024
# The whole request (files + form fields + multipart framing). Anything declared larger is refused before it is parsed
# or spooled to disk — the per-file check below only runs AFTER the upload has been received.
MAX_REQUEST_BYTES = MAX_FILES * MAX_FILE_BYTES + 512 * 1024
ALLOWED = {  # extension -> (content type, magic-bytes check)
    "png": ("image/png", lambda b: b.startswith(b"\x89PNG\r\n\x1a\n")),
    "jpg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    "jpeg": ("image/jpeg", lambda b: b.startswith(b"\xff\xd8\xff")),
    "gif": ("image/gif", lambda b: b[:6] in (b"GIF87a", b"GIF89a")),
    "webp": ("image/webp", lambda b: b[:4] == b"RIFF" and b[8:12] == b"WEBP"),
    "pdf": ("application/pdf", lambda b: b.startswith(b"%PDF-")),
    "txt": ("text/plain", lambda b: b"\x00" not in b),
}


def refuse_oversized_request(request):
    """HTTP 413 for a request that DECLARES a body larger than any legitimate ticket message, or declares nothing
    while claiming to be multipart/streamed (a chunked body has no honest size to trust)."""
    from rest_framework.exceptions import APIException

    class TooLarge(APIException):
        status_code = 413
        default_detail = "حجم الطلب أكبر من المسموح."
        default_code = "request_too_large"

    try:
        declared = int(request.META.get("CONTENT_LENGTH") or 0)
    except ValueError:
        declared = MAX_REQUEST_BYTES + 1
    if declared > MAX_REQUEST_BYTES:
        raise TooLarge()
    if not declared and "chunked" in (request.META.get("HTTP_TRANSFER_ENCODING") or "").lower():
        raise TooLarge()


def now():
    return timezone.now()


def sla_hours(priority):
    return int(get_setting(f"sla.{priority}_hours"))


def sla_base(ticket):
    last = ticket.events.filter(kind=TicketEvent.Kind.REOPENED).order_by("-created_at").first()
    return last.created_at if last else ticket.created_at


def compute_due(ticket, priority=None):
    return sla_base(ticket) + timedelta(hours=sla_hours(priority or ticket.priority))


def is_overdue(t):
    return bool(t.status in Ticket.WORKING and t.due_at and t.due_at < now())


def event(ticket, kind, actor=None, from_value="", to_value="", actor_name=""):
    return TicketEvent.objects.create(
        ticket=ticket, kind=kind, actor=actor if getattr(actor, "pk", None) else None,
        actor_name=actor_name or (getattr(actor, "name", "") if actor else ""), from_value=str(from_value)[:80],
        to_value=str(to_value)[:80])


def touch(ticket, **fields):
    for k, v in fields.items():
        setattr(ticket, k, v)
    ticket.last_activity_at = now()
    ticket.save(update_fields=[*fields, "last_activity_at", "updated_at"])


# ------------------------------------------------------------------ attachments
def validate_files(files):
    files = list(files or [])
    if len(files) > MAX_FILES:
        raise ValidationError({"files": [f"الحد الأقصى {MAX_FILES} ملفات في الرسالة."]})
    checked = []
    for f in files:
        name = (f.name or "file").replace("\\", "/").split("/")[-1][:150]
        ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
        if ext not in ALLOWED:
            raise ValidationError({"files": [f"نوع الملف غير مسموح ({name}). المسموح: png, jpg, gif, webp, pdf, txt."]})
        if f.size > MAX_FILE_BYTES:
            raise ValidationError({"files": [f"الملف «{name}» أكبر من 5 ميجابايت."]})
        head = f.read(16)
        f.seek(0)
        body = head if ext != "txt" else f.read(4096)
        f.seek(0)
        if not ALLOWED[ext][1](body):
            raise ValidationError({"files": [f"محتوى الملف «{name}» لا يطابق امتداده."]})
        checked.append((f, name, ALLOWED[ext][0]))
    return checked


def attach(message, checked):
    for f, name, ctype in checked:
        TicketAttachment.objects.create(message=message, file=f, original_name=name, content_type=ctype, size=f.size)


# ------------------------------------------------------------------ creation
def create_ticket(*, subject, description, category, kind, requester=None, requester_kind="other", name="", email="",
                  phone="", environment=None, source="customer", created_by=None, priority="medium", files=()):
    checked = validate_files(files)
    with transaction.atomic():
        t = Ticket.objects.create(
            subject=subject, description=description, category=category, kind=kind, priority=priority,
            requester=requester, requester_kind=requester_kind, requester_name=name, requester_email=email or "",
            requester_phone=phone or "", environment=environment, source=source, created_by=created_by)
        t.due_at = compute_due(t)
        t.save(update_fields=["due_at"])
        m = TicketMessage.objects.create(ticket=t, kind="customer", author=requester, author_name=name, body=description)
        attach(m, checked)
        event(t, TicketEvent.Kind.CREATED, created_by or requester, actor_name=name if not created_by else "")
    return t


# ------------------------------------------------------------------ messages
def staff_reply(ticket, actor, body, *, request_info=False, files=()):
    if ticket.status in REOPEN_FROM:
        raise ValidationError({"detail": ["التذكرة مغلقة أو محلولة. أعد فتحها أولًا للرد."]})
    checked = validate_files(files)
    with transaction.atomic():
        m = TicketMessage.objects.create(ticket=ticket, kind="agent", author=actor, author_name=actor.name, body=body)
        attach(m, checked)
        event(ticket, TicketEvent.Kind.REPLY, actor)
        fields = {"awaiting_team": False}
        if ticket.first_response_at is None:
            fields["first_response_at"] = now()
        new_status = S.WAITING if request_info else (S.IN_PROGRESS if ticket.status == S.OPEN else ticket.status)
        if new_status != ticket.status:
            event(ticket, TicketEvent.Kind.STATUS, actor, ticket.status, new_status)
            fields["status"] = new_status
        if ticket.assignee_id is None:  # answering a ticket nobody owns claims it
            fields["assignee"] = actor
            event(ticket, TicketEvent.Kind.ASSIGNED, actor, "", actor.name)
        touch(ticket, **fields)
    return m


def internal_note(ticket, actor, body, files=()):
    checked = validate_files(files)
    with transaction.atomic():
        m = TicketMessage.objects.create(ticket=ticket, kind="internal", author=actor, author_name=actor.name, body=body)
        attach(m, checked)
        event(ticket, TicketEvent.Kind.NOTE, actor)
        touch(ticket)
    return m


def customer_reply(ticket, user, body, files=()):
    checked = validate_files(files)
    with transaction.atomic():
        fields = {"awaiting_team": True}
        if ticket.status == S.CLOSED:
            days = int(get_setting("tickets.reopen_days"))
            if not ticket.closed_at or now() - ticket.closed_at > timedelta(days=days):
                raise ValidationError({"detail": ["انتهت مهلة إعادة فتح هذه التذكرة. أنشئ تذكرة جديدة."]})
        m = TicketMessage.objects.create(ticket=ticket, kind="customer", author=user, author_name=user.name, body=body)
        attach(m, checked)
        event(ticket, TicketEvent.Kind.CUSTOMER_REPLY, user)
        if ticket.status in REOPEN_FROM:
            _reopen_fields(ticket, fields, S.OPEN, user)
        elif ticket.status == S.WAITING:
            event(ticket, TicketEvent.Kind.STATUS, user, ticket.status, S.IN_PROGRESS)
            fields["status"] = S.IN_PROGRESS
        touch(ticket, **fields)
    return m


def _reopen_fields(ticket, fields, to, actor):
    event(ticket, TicketEvent.Kind.REOPENED, actor, ticket.status, to)
    fields.update(status=to, resolved_at=None, closed_at=None, reopen_count=ticket.reopen_count + 1)
    ticket.status = to  # for the due computation below
    fields["due_at"] = now() + timedelta(hours=sla_hours(ticket.priority))


# ------------------------------------------------------------------ status / priority / assignment
def change_status(ticket, actor, new, can_resolve, can_reply, request=None, note=""):
    new = str(new)
    if new not in S.values:
        raise ValidationError({"status": ["حالة غير معروفة."]})
    old = ticket.status
    if new == old:
        raise ValidationError({"status": ["التذكرة في هذه الحالة بالفعل."]})
    if new not in TRANSITIONS[old]:
        raise ValidationError({"status": ["هذا الانتقال غير مسموح في دورة حياة التذكرة."]})
    reopening = old in REOPEN_FROM and new in (S.OPEN, S.IN_PROGRESS)
    if (new in NEEDS_RESOLVE or reopening) and not can_resolve:
        raise PermissionDenied("حل التذكرة أو إغلاقها أو إعادة فتحها يتطلب صلاحية «حل التذاكر».")
    if not (can_resolve or can_reply):
        raise PermissionDenied("تغيير الحالة يتطلب صلاحية الرد على التذاكر.")
    with transaction.atomic():
        fields = {}
        if reopening:
            _reopen_fields(ticket, fields, new, actor)
        else:
            event(ticket, TicketEvent.Kind.STATUS, actor, old, new)
            fields["status"] = new
            if new == S.RESOLVED:
                fields["resolved_at"] = now()
            if new == S.CLOSED:
                fields["closed_at"] = now()
                if not ticket.resolved_at:
                    fields["resolved_at"] = now()
        if note:
            TicketMessage.objects.create(ticket=ticket, kind="internal", author=actor, author_name=actor.name, body=note)
        touch(ticket, **fields)
        audit.record(request, "ticket.reopen" if reopening else "ticket.status", "ticket", ticket.id, ticket.number,
                     {"status": old}, {"status": new})
    return ticket


def change_priority(ticket, actor, new, request=None):
    if new not in Ticket.Priority.values:
        raise ValidationError({"priority": ["أولوية غير معروفة."]})
    old = ticket.priority
    if new == old:
        raise ValidationError({"priority": ["التذكرة بهذه الأولوية بالفعل."]})
    with transaction.atomic():
        event(ticket, TicketEvent.Kind.PRIORITY, actor, old, new)
        touch(ticket, priority=new, due_at=compute_due(ticket, new))
        audit.record(request, "ticket.priority", "ticket", ticket.id, ticket.number, {"priority": old}, {"priority": new})
    return ticket


def change_category(ticket, actor, category, request=None):
    if not category.is_active:
        raise ValidationError({"category": ["هذا التصنيف غير مفعّل."]})
    old = ticket.category
    if old.pk == category.pk:
        return ticket
    with transaction.atomic():
        event(ticket, TicketEvent.Kind.CATEGORY, actor, old.name, category.name)
        touch(ticket, category=category)
        audit.record(request, "ticket.category", "ticket", ticket.id, ticket.number, {"category": old.name},
                     {"category": category.name})
    return ticket


def assign(ticket, actor, assignee, request=None):
    """`assignee` is a team User (already checked for being an active agent) or None to unassign."""
    old = ticket.assignee
    if (old and assignee and old.pk == assignee.pk) or (old is None and assignee is None):
        raise ValidationError({"assignee": ["لا تغيير في الإسناد."]})
    with transaction.atomic():
        event(ticket, TicketEvent.Kind.ASSIGNED, actor, old.name if old else "", assignee.name if assignee else "")
        touch(ticket, assignee=assignee)
        audit.record(request, "ticket.assign", "ticket", ticket.id, ticket.number,
                     {"assignee": old.name if old else None}, {"assignee": assignee.name if assignee else None})
    return ticket


def rate(ticket, user, rating, comment):
    if ticket.status not in REOPEN_FROM:
        raise ValidationError({"detail": ["يمكن التقييم بعد حل التذكرة فقط."]})
    if ticket.rating is not None:
        raise ValidationError({"detail": ["سبق تقييم هذه التذكرة."]})
    with transaction.atomic():
        event(ticket, TicketEvent.Kind.RATED, user, "", rating)
        touch(ticket, rating=rating, rating_comment=(comment or "")[:500], rated_at=now())
    return ticket


def active_category(pk):
    return TicketCategory.objects.filter(pk=pk, is_active=True).first()
