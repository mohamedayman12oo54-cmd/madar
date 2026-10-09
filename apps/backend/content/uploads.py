"""
Upload validation for teacher-uploaded video files.

The rule everywhere here: **never trust anything the client tells us about the
file**. The browser-supplied filename, extension and Content-Type are all
attacker-controlled, so they are checked but never relied on alone — the
decisive test is the file's own leading bytes.

What this defends against:
  * executable / script uploads (`.php`, `.exe`, `.sh`, double extensions like
    `clip.mp4.php`) — rejected by extension whitelist AND magic bytes;
  * path traversal and absolute paths in the filename (`../../etc/passwd`) —
    the client filename is discarded entirely; storage names are generated;
  * content-type spoofing — a `.mp4` whose bytes are a ZIP/ELF is rejected;
  * oversized uploads — capped before anything is written.
"""
import os
import secrets
import unicodedata

from django.conf import settings
from django.core.exceptions import ValidationError

# Container formats a browser <video> can actually play back.
ALLOWED_EXTENSIONS = {".mp4", ".m4v", ".webm", ".mov"}
ALLOWED_CONTENT_TYPES = {
    "video/mp4", "video/x-m4v", "video/webm", "video/quicktime",
}

# (offset, signature) pairs that identify a real media container.
_SIGNATURES = (
    (4, b"ftyp"),           # ISO-BMFF: mp4 / m4v / mov
    (0, b"\x1a\x45\xdf\xa3"),  # EBML: webm / mkv
)

# Leading bytes that must NEVER be accepted whatever the extension claims.
_EXECUTABLE_MAGIC = (
    b"MZ",            # Windows PE
    b"\x7fELF",       # Linux ELF
    b"#!",            # shell / interpreter script
    b"PK\x03\x04",    # zip / jar / office
    b"%PDF",
    b"<?php",
    b"<script",
    b"\xca\xfe\xba\xbe",  # java class / mach-o fat
)


def _read_head(upload, size=16):
    upload.seek(0)
    head = upload.read(size)
    upload.seek(0)
    return head or b""


def validate_video_upload(upload):
    """Raise ValidationError unless `upload` is a plausible video file.

    Order matters: cheap checks (size, extension) run before reading bytes.
    """
    if upload is None:
        raise ValidationError("لم يتم إرفاق ملف.")

    max_bytes = getattr(settings, "VIDEO_MAX_BYTES", 512 * 1024 * 1024)
    size = getattr(upload, "size", 0) or 0
    if size <= 0:
        raise ValidationError("الملف فارغ.")
    if size > max_bytes:
        raise ValidationError(f"حجم الفيديو يتجاوز الحد المسموح ({max_bytes // (1024 * 1024)} ميجابايت).")

    ext = os.path.splitext(upload.name or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise ValidationError("صيغة غير مدعومة. الصيغ المسموحة: MP4, M4V, WEBM, MOV.")

    # A double extension ("clip.mp4.php") only ever shows up in the part we
    # discard, but reject it explicitly so the attempt is visible, not silent.
    stem = os.path.basename(upload.name or "").lower()
    if any(part in stem for part in (".php", ".exe", ".sh", ".js", ".html", ".svg", ".bat", ".py")):
        raise ValidationError("اسم الملف يحتوي على امتداد غير مسموح.")

    content_type = (getattr(upload, "content_type", "") or "").split(";")[0].strip().lower()
    if content_type and content_type not in ALLOWED_CONTENT_TYPES:
        raise ValidationError("نوع الملف غير مدعوم.")

    head = _read_head(upload)
    if any(head.startswith(sig) for sig in _EXECUTABLE_MAGIC):
        raise ValidationError("الملف ليس فيديو صالحًا.")
    if not any(head[offset:offset + len(sig)] == sig for offset, sig in _SIGNATURES):
        raise ValidationError("محتوى الملف لا يطابق صيغة فيديو مدعومة.")
    return True


def safe_display_name(raw: str) -> str:
    """A printable, harmless version of the client filename — for DISPLAY only.
    It never reaches the filesystem."""
    name = os.path.basename((raw or "").replace("\\", "/")).strip()
    name = unicodedata.normalize("NFKC", name)
    name = "".join(ch for ch in name if ch.isprintable() and ch not in '\\/:*?"<>|')
    return (name or "video")[:120]


def storage_path(instance, filename):
    """Where the blob actually lands.

    The client filename is NOT used: the stored name is random, so traversal,
    collisions and extension tricks are impossible by construction, and the
    path cannot be guessed from outside.
    """
    ext = os.path.splitext(filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        ext = ".mp4"
    return f"videos/{instance.environment_id}/{secrets.token_urlsafe(24)}{ext}"
