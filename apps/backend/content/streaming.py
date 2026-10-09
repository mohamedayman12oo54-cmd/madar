"""
Protected playback for uploaded videos.

There is **no public URL for any video file**. MEDIA_ROOT is not web-served and
the stored filename is random, so the only way to obtain bytes is:

    1. ask for a ticket  ->  the server checks you are allowed to watch THIS
       item right now (role, environment, active enrolment, targeting, and that
       the item is published);
    2. play the ticket   ->  the server re-checks the signature, the expiry,
       and that the ticket belongs to the caller, then streams.

The ticket is a signed payload (Django's `TimestampSigner`, keyed on
SECRET_KEY), so it cannot be forged or edited, and it carries the viewer id —
copying a link to a friend does not work, because the ticket is re-checked
against whoever presents it. Tickets expire in minutes, and because the check
is repeated at stream time, revoking access (unpublishing, un-targeting,
deactivating an enrolment, deleting the item) takes effect immediately even
for a ticket that has not yet expired.

Range requests are honoured so the player can seek without downloading the
whole file, and `X-Accel-Redirect` can hand the actual byte-pushing to nginx
so Django is not in the data path at scale.
"""
import os
import re

from django.conf import settings
from django.core.signing import BadSignature, SignatureExpired, TimestampSigner
from django.http import FileResponse, Http404, HttpResponse, StreamingHttpResponse

SIGNER_SALT = "content.video.playback"
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
CHUNK = 64 * 1024


def issue_ticket(item_id: int, viewer_id: int) -> str:
    """A short-lived, signed permission to stream ONE item as ONE viewer."""
    return TimestampSigner(salt=SIGNER_SALT).sign(f"{item_id}:{viewer_id}")


def read_ticket(ticket: str, viewer_id: int) -> int:
    """Return the item id a valid ticket authorises, or raise Http404.

    A tampered signature, an expired ticket, or a ticket issued to a different
    viewer are all indistinguishable to the caller — no oracle.
    """
    ttl = getattr(settings, "VIDEO_PLAYBACK_TTL_SECONDS", 300)
    try:
        raw = TimestampSigner(salt=SIGNER_SALT).unsign(ticket or "", max_age=ttl)
    except (BadSignature, SignatureExpired):
        raise Http404
    try:
        item_id, signed_viewer = (int(part) for part in raw.split(":"))
    except (ValueError, TypeError):
        raise Http404
    if signed_viewer != viewer_id:
        raise Http404  # a shared/stolen link is useless to anyone else
    return item_id


def _file_iterator(path, start, length):
    with open(path, "rb") as fh:
        fh.seek(start)
        remaining = length
        while remaining > 0:
            chunk = fh.read(min(CHUNK, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def stream_file(item, request):
    """Stream `item.video_file`, honouring HTTP Range so the player can seek."""
    field = item.video_file
    if not field:
        raise Http404
    path = field.path
    if not os.path.exists(path):
        raise Http404
    size = os.path.getsize(path)
    content_type = item.content_type or "video/mp4"

    # Behind nginx: let the web server push the bytes. The internal location
    # must NOT be reachable from outside (`internal;` in the nginx config).
    prefix = getattr(settings, "VIDEO_XACCEL_PREFIX", "")
    if prefix:
        response = HttpResponse(status=200, content_type=content_type)
        response["X-Accel-Redirect"] = f"{prefix.rstrip('/')}/{field.name}"
        response["Accept-Ranges"] = "bytes"
        _harden(response, item)
        return response

    range_header = request.META.get("HTTP_RANGE", "")
    match = _RANGE_RE.match(range_header) if range_header else None
    if match:
        start = int(match.group(1) or 0)
        end = int(match.group(2)) if match.group(2) else size - 1
        start = max(0, min(start, size - 1))
        end = max(start, min(end, size - 1))
        length = end - start + 1
        response = StreamingHttpResponse(
            _file_iterator(path, start, length), status=206, content_type=content_type)
        response["Content-Range"] = f"bytes {start}-{end}/{size}"
        response["Content-Length"] = str(length)
    else:
        response = FileResponse(open(path, "rb"), content_type=content_type)
        response["Content-Length"] = str(size)

    response["Accept-Ranges"] = "bytes"
    _harden(response, item)
    return response


def _harden(response, item):
    # Play inline; never offer the original file as a download, and never let
    # a browser sniff the body into something executable. Private caching only,
    # so a shared proxy can't hand the bytes to the next student.
    response["Content-Disposition"] = "inline"
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, no-store, max-age=0"
    return response
