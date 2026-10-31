"""
Protected playback for uploaded videos.

There is **no public URL for any video file**. MEDIA_ROOT is not web-served and
the stored filename is random, so the only way to obtain bytes is:

    1. ask for a ticket  ->  the server checks you are allowed to watch THIS
       item right now (role, environment, active enrolment, targeting, and that
       the item is published);
    2. play the ticket   ->  the server re-checks the signature and the expiry,
       then re-checks the named viewer's access to the item, then streams.

The ticket is a signed payload (Django's `TimestampSigner`, keyed on
SECRET_KEY), so it cannot be forged or edited. It names ONE item, the viewer
it was issued to and (optionally) one rendition, and it expires in minutes.

A `<video>` element cannot send an Authorization header, so the stream
endpoint accepts the ticket ALONE: it is a short-lived BEARER credential.
Anyone who holds a LIVE ticket URL can stream that one item until it expires;
the URL must therefore never be logged or shared. What still protects the content
is that the stream view re-checks the named viewer's authorisation against live
data on every request, so revoking access (unpublishing, un-targeting,
deactivating an enrolment, deleting the item) takes effect immediately even
for a ticket that has not yet expired. See SECURITY-AUDIT.md, "Playback URLs
are now bearer credentials".

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
# A study document (PDF) has its OWN salt: a document ticket can never be replayed against the
# video stream endpoint, nor a video ticket against the document one.
DOCUMENT_SALT = "content.document.view"
_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")
CHUNK = 64 * 1024


def issue_ticket(item_id: int, viewer_id: int, height: int | None = None, salt: str = SIGNER_SALT) -> str:
    """A short-lived, signed permission to stream ONE item as ONE viewer.

    `height` (e.g. 720) names one transcoded rendition; without it the ticket
    is for the original file. The height is INSIDE the signed payload, so a
    client cannot edit a 360p ticket into a 1080p one.
    """
    payload = f"{item_id}:{viewer_id}" if not height else f"{item_id}:{viewer_id}:{int(height)}"
    return TimestampSigner(salt=salt).sign(payload)


def resolve_ticket_full(ticket: str, salt: str = SIGNER_SALT):
    """`(item_id, viewer_id, height_or_None)` for a valid ticket, else Http404."""
    ttl = getattr(settings, "VIDEO_PLAYBACK_TTL_SECONDS", 300)
    try:
        raw = TimestampSigner(salt=salt).unsign(ticket or "", max_age=ttl)
        parts = [int(part) for part in raw.split(":")]
        if len(parts) not in (2, 3):
            raise ValueError
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        raise Http404
    return parts[0], parts[1], (parts[2] if len(parts) == 3 else None)


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


def stream_file(item, request, field=None, content_type=None):
    """Stream `item.video_file` (or a given rendition's file), honouring HTTP
    Range so the player can seek."""
    field = field if field is not None else item.video_file
    if not field:
        raise Http404
    path = field.path
    if not os.path.exists(path):
        raise Http404
    size = os.path.getsize(path)
    content_type = content_type or item.content_type or "video/mp4"

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
