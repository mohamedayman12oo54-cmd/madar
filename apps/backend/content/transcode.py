"""
Quality ladder for uploaded videos (360p / 480p / 720p / 1080p), via ffmpeg.

Security notes — this runs a subprocess on files users uploaded, so:
  * `subprocess.run` with an ARGUMENT LIST, never a shell: nothing user-supplied
    is ever interpreted by a shell.
  * The only inputs are server-generated: the stored (random) source path and a
    height drawn from a fixed whitelist. The client filename never reaches ffmpeg.
  * A hard timeout per rendition, and the container is already magic-byte
    validated before we get here.
  * Only heights STRICTLY below the source are produced (no upscaling).
  * If ffmpeg/ffprobe is missing or the file is unreadable we do nothing — the
    original keeps playing. Failure here must never break an upload.
  * If the teacher replaces the video while we are encoding, the stale output is
    discarded instead of being attached to the new file.
"""
import logging
import os
import shutil
import subprocess
import threading

from django.conf import settings
from django.db import close_old_connections

log = logging.getLogger(__name__)

LADDER = (360, 480, 720, 1080)


def _bin(name):
    return shutil.which(name)


def probe_height(path):
    """Height in pixels of the first video stream, or None."""
    ffprobe = _bin("ffprobe")
    if not ffprobe:
        return None
    try:
        out = subprocess.run(
            [ffprobe, "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=height",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=30, check=False)
        return int(out.stdout.strip().split(",")[0]) if out.returncode == 0 else None
    except (subprocess.SubprocessError, ValueError, OSError):
        return None


def heights_for(source_height):
    return [h for h in LADDER if source_height and h < source_height]


def _encode(src, dst, height):
    timeout = getattr(settings, "VIDEO_TRANSCODE_TIMEOUT", 3600)
    cmd = [_bin("ffmpeg"), "-nostdin", "-y", "-v", "error", "-i", src,
           "-vf", f"scale=-2:{int(height)}",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", dst]
    return subprocess.run(cmd, capture_output=True, timeout=timeout, check=False).returncode == 0


def build_renditions(item_id):
    """Create the missing lower-quality copies for one item. Returns heights made."""
    from django.core.files.base import ContentFile

    from .models import ContentItem, VideoRendition
    from .uploads import rendition_path

    if not _bin("ffmpeg"):
        return []
    item = ContentItem.objects.filter(pk=item_id).first()
    if not item or not item.video_file:
        return []
    source_name = item.video_file.name
    try:
        src = item.video_file.path
    except (ValueError, NotImplementedError):
        return []
    if not os.path.exists(src):
        return []

    made = []
    for h in heights_for(probe_height(src)):
        if item.renditions.filter(height=h).exists():
            continue
        rel = rendition_path(VideoRendition(item=item, height=h), "x.mp4")
        dst = os.path.join(settings.MEDIA_ROOT, rel)
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        try:
            ok = _encode(src, dst, h)
        except (subprocess.SubprocessError, OSError):
            ok = False
        if not ok or not os.path.exists(dst):
            if os.path.exists(dst):
                os.remove(dst)
            log.warning("transcode failed item=%s height=%s", item_id, h)
            continue
        # The video may have been replaced/deleted while we were encoding.
        current = ContentItem.objects.filter(pk=item_id).values_list("video_file", flat=True).first()
        if current != source_name:
            os.remove(dst)
            break
        VideoRendition.objects.update_or_create(
            item=item, height=h, defaults={"video_file": rel, "file_size": os.path.getsize(dst)})
        made.append(h)
    return made


def delete_renditions(item):
    """Drop every rendition (rows + blobs) — used when the original goes away."""
    for r in list(item.renditions.all()):
        r.delete()          # post_delete removes the blob


def schedule_renditions(item_id):
    """Kick off encoding without holding the upload request open."""
    if not getattr(settings, "VIDEO_TRANSCODE", True):
        return
    if getattr(settings, "VIDEO_TRANSCODE_SYNC", False):
        build_renditions(item_id)
        return

    def run():
        try:
            build_renditions(item_id)
        except Exception:                                  # never crash the worker thread
            log.exception("rendition build crashed item=%s", item_id)
        finally:
            close_old_connections()

    threading.Thread(target=run, daemon=True, name=f"renditions-{item_id}").start()
