"""
Lesson-video transcription (pipeline step 2: video -> text with timestamps).

Same shape as the other Madar-owned provider interfaces (content/video.py,
ai/providers.py): the model that does the work is an implementation detail
behind `Transcriber`. The default, `FasterWhisperTranscriber`, runs locally —
no API key, and the lesson audio never leaves the server.

Lifecycle (mirrors the AI operations): pending -> processing -> completed |
failed. The upload returns immediately; the slow part runs in a background
thread (default) or in `manage.py transcribe_videos` (TRANSCRIPTION_BACKGROUND
= "worker"). The result is persisted on `Transcript`, which is the source of
truth; a failure is explicit and retryable, and never leaves half a transcript.
"""
import logging
import threading

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import ContentItem, Transcript

log = logging.getLogger(__name__)


class TranscriptionError(Exception):
    """A failure whose message is safe and useful to show to the teacher."""


class Transcriber:
    name = ""

    def transcribe(self, path: str, language: str = "") -> dict:  # pragma: no cover - interface
        """-> {"text", "language", "duration", "segments": [{"start","end","text"}]}"""
        raise NotImplementedError


class FasterWhisperTranscriber(Transcriber):
    name = "faster_whisper"
    _model = None
    _lock = threading.Lock()

    @classmethod
    def _load(cls):
        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:
            raise TranscriptionError(
                "مكتبة التفريغ غير مثبّتة على الخادم. نفّذ: pip install faster-whisper"
            ) from exc
        with cls._lock:
            if cls._model is None:
                cls._model = WhisperModel(
                    getattr(settings, "TRANSCRIPTION_MODEL", "small"),
                    device=getattr(settings, "TRANSCRIPTION_DEVICE", "cpu"),
                    compute_type=getattr(settings, "TRANSCRIPTION_COMPUTE_TYPE", "int8"),
                )
        return cls._model

    def transcribe(self, path, language=""):
        model = self._load()
        try:
            segments, info = model.transcribe(
                path, language=language or None, vad_filter=True, beam_size=5)
            out, parts = [], []
            for seg in segments:  # a generator: decoding happens while we iterate
                text = (seg.text or "").strip()
                if not text:
                    continue
                parts.append(text)
                out.append({"start": round(seg.start, 2), "end": round(seg.end, 2), "text": text})
        except TranscriptionError:
            raise
        except Exception as exc:
            log.exception("faster-whisper failed on %s", path)
            raise TranscriptionError("تعذّر قراءة الصوت من ملف الفيديو.") from exc
        return {
            "text": " ".join(parts), "language": info.language or "",
            "duration": info.duration, "segments": out,
        }


_TRANSCRIBERS = {FasterWhisperTranscriber.name: FasterWhisperTranscriber}


def get_transcriber() -> Transcriber:
    name = getattr(settings, "TRANSCRIPTION_PROVIDER", FasterWhisperTranscriber.name)
    try:
        return _TRANSCRIBERS[name]()
    except KeyError:
        raise TranscriptionError(f"Unknown TRANSCRIPTION_PROVIDER {name!r}")


# --------------------------------------------------------------------- run --
def run_transcription(transcript_id) -> None:
    """Do the work for one row. Safe to call twice: only the caller that wins
    the pending/processing -> processing claim proceeds."""
    claimed = Transcript.objects.filter(
        pk=transcript_id, status__in=[Transcript.Status.PENDING, Transcript.Status.PROCESSING],
    ).update(status=Transcript.Status.PROCESSING, started_at=timezone.now(), error="")
    if not claimed:
        return
    row = Transcript.objects.select_related("item").get(pk=transcript_id)
    try:
        item = row.item
        if not item.video_file:
            raise TranscriptionError("لا يوجد ملف فيديو مرفوع لهذا المحتوى.")
        transcriber = get_transcriber()
        result = transcriber.transcribe(
            item.video_file.path, getattr(settings, "TRANSCRIPTION_LANGUAGE", ""))
        text = (result.get("text") or "").strip()
        if not text:
            raise TranscriptionError("لم يتم العثور على كلام في الفيديو.")
    except TranscriptionError as exc:
        _fail(transcript_id, str(exc))
        return
    except Exception:
        log.exception("transcription failed for transcript %s", transcript_id)
        _fail(transcript_id, "حدث خطأ غير متوقع أثناء تحويل الفيديو إلى نص.")
        return

    duration = result.get("duration")
    Transcript.objects.filter(pk=transcript_id).update(
        status=Transcript.Status.COMPLETED, text=text, language=result.get("language", ""),
        segments=result.get("segments", []),
        duration_seconds=int(duration) if duration else None,
        provider=transcriber.name, error="", completed_at=timezone.now(),
    )


def _fail(transcript_id, message):
    Transcript.objects.filter(pk=transcript_id).update(
        status=Transcript.Status.FAILED, error=message[:1000], completed_at=timezone.now())


# ---------------------------------------------------------------- dispatch --
_running = set()
_running_lock = threading.Lock()


def _thread_main(transcript_id):
    try:
        run_transcription(transcript_id)
    finally:
        close_old_connections()
        with _running_lock:
            _running.discard(transcript_id)


def _start_thread(transcript_id):
    with _running_lock:
        if transcript_id in _running:
            return
        _running.add(transcript_id)
    threading.Thread(target=_thread_main, args=(transcript_id,), daemon=True,
                     name=f"transcribe-{transcript_id}").start()


def background_mode():
    return getattr(settings, "TRANSCRIPTION_BACKGROUND", "thread")


def request_transcription(item_id):
    """(Re)start transcription for an item that has an uploaded file. Resets any
    previous result — a replaced video must not keep the old lesson's text."""
    item = ContentItem.objects.get(pk=item_id)
    if not item.video_file:
        return None
    row, _ = Transcript.objects.get_or_create(item=item, defaults={"environment_id": item.environment_id})
    Transcript.objects.filter(pk=row.pk).update(
        status=Transcript.Status.PENDING, text="", segments=[], language="", duration_seconds=None,
        provider="", error="", started_at=None, completed_at=None)
    row.refresh_from_db()
    if background_mode() == "thread":
        transaction.on_commit(lambda: _start_thread(row.pk))
    return row


def ensure_running(row):
    """Called when the teacher polls. If the server restarted mid-transcription
    the thread died with it, leaving the row 'processing' forever — so a
    pending/processing row with no live thread is picked up again here."""
    if background_mode() != "thread":
        return row
    if row.status not in (Transcript.Status.PENDING, Transcript.Status.PROCESSING):
        return row
    with _running_lock:
        alive = row.pk in _running
    if not alive:
        _start_thread(row.pk)
    return row
