"""
Lesson-video transcription (pipeline step 2: video -> text with timestamps).

Same shape as the other Madar-owned provider interfaces (content/video.py,
ai/providers.py): the model that does the work is an implementation detail
behind `Transcriber`. The default pipeline tries the hosted
`GroqWhisperTranscriber` first (Groq's free-tier, OpenAI-compatible Whisper
API) and falls back to the local `FasterWhisperTranscriber` (via
`FallbackTranscriber`) when the API is rate limited, times out, is otherwise
unavailable, or is not configured — so a lesson is never left untranscribed
just because the external API had a bad moment. `FasterWhisperTranscriber`
remains available standalone (no API key, audio never leaves the server) by
setting TRANSCRIPTION_PROVIDER=faster_whisper.

Lifecycle (mirrors the AI operations): pending -> processing -> completed |
failed. The upload returns immediately; the slow part runs in a background
thread (default) or in `manage.py transcribe_videos` (TRANSCRIPTION_BACKGROUND
= "worker"). The result is persisted on `Transcript`, which is the source of
truth; a failure is explicit and retryable, and never leaves half a transcript.
"""
import http.client
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import urllib.error
import urllib.request
import uuid

from django.conf import settings
from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import ContentItem, Transcript

log = logging.getLogger(__name__)

# Defence in depth for logs: mask anything shaped like a vendor API key even
# if it was never meant to be logged in the first place.
_GROQ_KEY_RE = re.compile(r"gsk_[A-Za-z0-9]{20,}")


def _redact(text, *secrets):
    text = str(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "[redacted]")
    return _GROQ_KEY_RE.sub("[redacted]", text)


class TranscriptionError(Exception):
    """A failure whose message is safe and useful to show to the teacher."""


class ExternalSTTError(Exception):
    """Internal signal from an external STT adapter (category + HTTP status,
    for logs only). Never shown to the user directly — a `FallbackTranscriber`
    catches it and either falls back or lets `TranscriptionError` carry the
    user-safe message instead."""
    category = "error"

    def __init__(self, message, *, category=None, status=None):
        super().__init__(message)
        if category:
            self.category = category
        self.status = status


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


# ------------------------------------------------------- external STT (API) --
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """An API endpoint never legitimately redirects, and urllib would otherwise
    resend the Authorization header to wherever `Location` points."""

    def redirect_request(self, *args, **kwargs):
        return None


def _extract_audio(path):
    """-> (audio_path, is_temp_file). Shrinks the upload to a small, mono,
    low-bitrate mp3 — well under the external API's size limit even for a long
    lecture — via the same ffmpeg argument-list convention as
    `content/transcode.py` (no shell; the only inputs are a server-generated
    path and fixed flags). Falls back to the original file, untouched, when
    ffmpeg is unavailable: the external API also accepts common video
    containers directly, just at a larger upload size."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return path, False
    fd, dst = tempfile.mkstemp(suffix=".mp3", prefix="stt-")
    os.close(fd)
    cmd = [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", path,
           "-vn", "-ac", "1", "-ar", "16000", "-b:a", "64k", dst]
    try:
        ok = subprocess.run(cmd, capture_output=True, timeout=600, check=False).returncode == 0
    except (subprocess.SubprocessError, OSError):
        ok = False
    if not ok or not os.path.getsize(dst):
        if os.path.exists(dst):
            os.remove(dst)
        return path, False
    return dst, True


def _parse_groq_error(raw):
    """-> message. Tolerant of a non-JSON body. Groq's audio-transcription
    endpoint is OpenAI-compatible, including this `{"error": {"message": ...}}`
    shape."""
    try:
        err = json.loads(raw.decode("utf-8", "replace")).get("error", {})
        if not isinstance(err, dict):
            return ""
    except (ValueError, AttributeError):
        return ""
    return err.get("message") if isinstance(err.get("message"), str) else ""


def _multipart_post(url, headers, fields, filename, file_bytes, timeout):
    """One POST with a hand-built multipart/form-data body (stdlib only — same
    "no SDK" convention as `ai.gemini`, so nothing retries behind our back).
    Returns (status, lower-cased headers, body bytes) for ANY HTTP status;
    raises `ExternalSTTError` only for transport-level failures."""
    boundary = uuid.uuid4().hex
    body = io.BytesIO()
    for key, value in fields.items():
        body.write(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{key}"\r\n\r\n{value}\r\n'.encode())
    body.write(
        f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f'Content-Type: application/octet-stream\r\n\r\n'.encode())
    body.write(file_bytes)
    body.write(f"\r\n--{boundary}--\r\n".encode())
    payload = body.getvalue()
    headers = {**headers, "Content-Type": f"multipart/form-data; boundary={boundary}"}
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(req, timeout=timeout) as resp:
            return resp.status, {k.lower(): v for k, v in resp.headers.items()}, resp.read()
    except urllib.error.HTTPError as exc:
        try:
            raw = exc.read()
        except OSError:
            raw = b""
        finally:
            exc.close()
        return exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, raw
    except TimeoutError as exc:
        raise ExternalSTTError("The request to the STT provider timed out.", category="timeout") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise ExternalSTTError("The request to the STT provider timed out.", category="timeout") from exc
        raise ExternalSTTError(
            f"Could not reach the STT provider ({type(exc.reason).__name__}).", category="network") from exc
    except (OSError, http.client.HTTPException) as exc:
        raise ExternalSTTError(
            f"Connection to the STT provider failed ({type(exc).__name__}).", category="network") from exc


class GroqWhisperTranscriber(Transcriber):
    """Hosted Whisper transcription via Groq's REST API — the default PRIMARY
    provider. Groq's free tier runs `whisper-large-v3-turbo` (and
    `whisper-large-v3`) behind an OpenAI-compatible endpoint, so this adapter
    is a plain multipart POST, same as `ai.gemini.GeminiClient`'s "no SDK"
    convention. Swapping the vendor later means writing another `Transcriber`
    and adding it to `_TRANSCRIBERS`, not touching the fallback logic or the
    quiz pipeline downstream."""
    name = "groq_whisper_api"
    API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

    def __init__(self, *, api_key=None, model=None, timeout=None, transport=None):
        self._api_key = (api_key if api_key is not None else getattr(settings, "GROQ_API_KEY", "")).strip()
        self._model = (model or getattr(settings, "GROQ_STT_MODEL", "whisper-large-v3-turbo")).strip()
        self._timeout = timeout or getattr(settings, "GROQ_STT_TIMEOUT_SECONDS", 120)
        self._transport = transport or _multipart_post

    @classmethod
    def is_configured(cls):
        return bool(getattr(settings, "GROQ_API_KEY", "").strip())

    def transcribe(self, path, language=""):
        if not self._api_key:
            raise ExternalSTTError("GROQ_API_KEY is not set.", category="config")
        audio_path, is_temp = _extract_audio(path)
        try:
            with open(audio_path, "rb") as fh:
                audio_bytes = fh.read()
        finally:
            if is_temp:
                try:
                    os.remove(audio_path)
                except OSError:
                    pass
        fields = {"model": self._model, "response_format": "verbose_json"}
        if language:
            fields["language"] = language
        headers = {"Authorization": f"Bearer {self._api_key}"}
        status, resp_headers, raw = self._transport(
            self.API_URL, headers, fields, "audio.mp3", audio_bytes, self._timeout)
        if status != 200:
            raise self._error_for(status, resp_headers, raw)
        return self._parse(raw)

    def _error_for(self, status, headers, raw):
        message = _parse_groq_error(raw)
        safe = _redact(message, self._api_key)[:200]
        detail = f"Groq STT HTTP {status}" + (f": {safe}" if safe else "")
        if status in (401, 403):
            return ExternalSTTError(detail, category="auth", status=status)
        if status == 429:
            return ExternalSTTError(detail, category="rate_limit", status=status)
        if status == 408 or status >= 500:
            return ExternalSTTError(detail, category="provider", status=status)
        return ExternalSTTError(detail, category="bad_request", status=status)

    def _parse(self, raw):
        try:
            data = json.loads(raw.decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise ExternalSTTError(
                "Groq STT returned a response that is not valid JSON.", category="malformed_response") from exc
        text = data.get("text") if isinstance(data, dict) else None
        if not isinstance(text, str):
            raise ExternalSTTError(
                "Groq STT returned an unexpected response shape.", category="malformed_response")
        segments = []
        for seg in data.get("segments") or []:
            if isinstance(seg, dict) and isinstance(seg.get("text"), str):
                segments.append({
                    "start": round(float(seg.get("start") or 0), 2),
                    "end": round(float(seg.get("end") or 0), 2),
                    "text": seg["text"].strip(),
                })
        return {
            "text": text.strip(), "language": data.get("language") or "",
            "duration": data.get("duration"), "segments": segments,
        }


class FallbackTranscriber(Transcriber):
    """Primary: an external STT API. Falls back to a local transcriber when
    the primary is unconfigured, rate limited, times out, or is otherwise
    unavailable — so a lesson is never left untranscribed over a transient API
    problem. If the fallback also fails, its `TranscriptionError` (a safe,
    teacher-facing message) is what the caller sees."""
    name = "external_stt_with_fallback"

    def __init__(self, primary: Transcriber | None, fallback: Transcriber):
        self._primary = primary
        self._fallback = fallback

    def transcribe(self, path, language=""):
        if self._primary is not None:
            try:
                result = self._primary.transcribe(path, language)
                result.setdefault("provider", self._primary.name)
                return result
            except ExternalSTTError as exc:
                log.warning(
                    "external STT failed (category=%s status=%s), falling back to %s: %s",
                    exc.category, exc.status, self._fallback.name, exc,
                )
            except Exception:
                log.exception(
                    "external STT raised an unexpected error, falling back to %s", self._fallback.name)
        result = self._fallback.transcribe(path, language)
        result.setdefault("provider", self._fallback.name)
        return result


def _external_with_local_fallback():
    primary = GroqWhisperTranscriber() if GroqWhisperTranscriber.is_configured() else None
    fallback = _TRANSCRIBERS[FasterWhisperTranscriber.name]()
    return FallbackTranscriber(primary, fallback)


_TRANSCRIBERS = {
    FasterWhisperTranscriber.name: FasterWhisperTranscriber,
    GroqWhisperTranscriber.name: _external_with_local_fallback,
}


def get_transcriber() -> Transcriber:
    name = getattr(settings, "TRANSCRIPTION_PROVIDER", GroqWhisperTranscriber.name)
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
        provider=result.get("provider") or transcriber.name, error="", completed_at=timezone.now(),
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
