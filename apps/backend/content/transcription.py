"""
Lesson-video transcription (pipeline step 2: video -> text with timestamps).

Same shape as the other Madar-owned provider interfaces (content/video.py,
ai/providers.py): the model that does the work is an implementation detail
behind `Transcriber`. The ONLY active provider is the hosted
`GroqWhisperTranscriber` (Groq's OpenAI-compatible Whisper API). When it is
rate limited, unavailable, or not configured the transcript is marked failed
with a teacher-facing message and can be retried; nothing runs locally.

FROZEN: `FasterWhisperTranscriber` and `FallbackTranscriber` are kept in this
file but are deliberately absent from `_TRANSCRIBERS`, so the product cannot
reach them. To unfreeze, register them there again.

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
import time
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


def _ms(seconds):
    return int(round(seconds * 1000))


class TranscriptionError(Exception):
    """A failure whose message is safe and useful to show to the teacher."""


class ExternalSTTError(Exception):
    """Internal signal from an external STT adapter (category + HTTP status,
    for logs only). Never shown to the user directly — `run_transcription`
    turns the category into a message from `_STT_FAILURE_MESSAGES`."""
    category = "error"

    def __init__(self, message, *, category=None, status=None, hint=None):
        super().__init__(message)
        if category:
            self.category = category
        self.status = status
        self.hint = hint  # "no_ffmpeg": too big only because the audio could not be pulled out of the video
        self.elapsed_ms = None


class Transcriber:
    name = ""

    def transcribe(self, path: str, language: str = "") -> dict:  # pragma: no cover - interface
        """-> {"text", "language", "duration", "segments": [{"start","end","text"}]}"""
        raise NotImplementedError


class FasterWhisperTranscriber(Transcriber):
    """FROZEN: not registered in `_TRANSCRIBERS` (see the module docstring)."""
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
        started = time.monotonic()
        model = self._load()
        loaded = time.monotonic()
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
        done = time.monotonic()
        return {
            "text": " ".join(parts), "language": info.language or "",
            "duration": info.duration, "segments": out,
            "timings_ms": {"model_load": _ms(loaded - started), "decode": _ms(done - loaded),
                           "total": _ms(done - started)},
        }


# ------------------------------------------------------- external STT (API) --
class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """An API endpoint never legitimately redirects, and urllib would otherwise
    resend the Authorization header to wherever `Location` points."""

    def redirect_request(self, *args, **kwargs):
        return None


_AUDIO_BITRATE = 64_000  # bits per second of the mono mp3 we send (8000 bytes of audio per second)


def _ffmpeg_path():
    """The ffmpeg to use, or None. In order: FFMPEG_BINARY (settings), the one on PATH, then the copy bundled
    with the `imageio-ffmpeg` package (so a machine with no system ffmpeg still works after `pip install`)."""
    configured = (getattr(settings, "FFMPEG_BINARY", "") or "").strip()
    if configured and os.path.isfile(configured):
        return configured
    found = shutil.which("ffmpeg")
    if found:
        return found
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        return bundled if bundled and os.path.isfile(bundled) else None
    except Exception:  # not installed / no binary for this platform
        return None


def _extract_audio(path):
    """-> (audio_path, is_temp_file). Shrinks the upload to a small, mono,
    low-bitrate mp3 — well under the external API's size limit even for a long
    lecture — via the same ffmpeg argument-list convention as
    `content/transcode.py` (no shell; the only inputs are a server-generated
    path and fixed flags). Falls back to the original file, untouched, when
    ffmpeg is unavailable: the external API also accepts common video
    containers directly, just at a larger upload size."""
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return path, False
    fd, dst = tempfile.mkstemp(suffix=".mp3", prefix="stt-")
    os.close(fd)
    cmd = [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", path,
           "-vn", "-ac", "1", "-ar", "16000", "-b:a", str(_AUDIO_BITRATE // 1000) + "k", dst]
    try:
        ok = subprocess.run(cmd, capture_output=True, timeout=600, check=False).returncode == 0
    except (subprocess.SubprocessError, OSError):
        ok = False
    if not ok or not os.path.getsize(dst):
        if os.path.exists(dst):
            os.remove(dst)
        return path, False
    return dst, True


def _split_audio(audio_path, max_bytes):
    """Cut a long mp3 into pieces that each fit under `max_bytes`: -> [(piece_path, start_offset_seconds)].
    The piece length is derived from the fixed bitrate with a 20% margin, and every piece is checked afterwards.
    Raises ExternalSTTError("too_large") if ffmpeg cannot do it. The caller removes the pieces."""
    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        raise ExternalSTTError("Cannot split the audio: ffmpeg is unavailable.", category="too_large", hint="no_ffmpeg")
    seconds = max(1, int(max_bytes * 0.8 / (_AUDIO_BITRATE / 8)))
    workdir = tempfile.mkdtemp(prefix="stt-parts-")
    pattern = os.path.join(workdir, "part%04d.mp3")
    try:
        ok = subprocess.run(
            [ffmpeg, "-nostdin", "-y", "-v", "error", "-i", audio_path, "-f", "segment",
             "-segment_time", str(seconds), "-c", "copy", pattern],
            capture_output=True, timeout=600, check=False).returncode == 0
    except (subprocess.SubprocessError, OSError):
        ok = False
    parts = sorted(os.path.join(workdir, n) for n in os.listdir(workdir))
    if not ok or not parts or any(os.path.getsize(p) > max_bytes for p in parts):
        for p in parts:
            os.remove(p)
        os.rmdir(workdir)
        raise ExternalSTTError("Could not split the audio into pieces under the upload limit.", category="too_large")
    return [(p, i * seconds) for i, p in enumerate(parts)]


def _remove_files(paths):
    for p in paths:
        try:
            os.remove(p)
        except OSError:
            pass
        parent = os.path.dirname(p)
        if os.path.basename(parent).startswith("stt-parts-"):
            try:
                os.rmdir(parent)
            except OSError:
                pass


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
    """Hosted Whisper transcription via Groq's REST API — the only active
    provider. Groq's free tier runs `whisper-large-v3-turbo` (and
    `whisper-large-v3`) behind an OpenAI-compatible endpoint, so this adapter
    is a plain multipart POST, same as `ai.gemini.GeminiClient`'s "no SDK"
    convention. Swapping the vendor later means writing another `Transcriber`
    and adding it to `_TRANSCRIBERS`, not touching the quiz pipeline
    downstream."""
    name = "groq_whisper_api"
    API_URL = "https://api.groq.com/openai/v1/audio/transcriptions"

    def __init__(self, *, api_key=None, model=None, timeout=None, transport=None, max_upload_mb=None):
        self._api_key = (api_key if api_key is not None else getattr(settings, "GROQ_API_KEY", "")).strip()
        self._model = (model or getattr(settings, "GROQ_STT_MODEL", "whisper-large-v3-turbo")).strip()
        self._timeout = timeout or getattr(settings, "GROQ_STT_TIMEOUT_SECONDS", 120)
        self._transport = transport or _multipart_post
        self._max_upload_bytes = (max_upload_mb or getattr(settings, "GROQ_STT_MAX_UPLOAD_MB", 25)) * 1024 * 1024

    @classmethod
    def is_configured(cls):
        return bool(getattr(settings, "GROQ_API_KEY", "").strip())

    def transcribe(self, path, language=""):
        if not self._api_key:
            raise ExternalSTTError("GROQ_API_KEY is not set.", category="config")
        started = time.monotonic()
        audio_path, is_temp = _extract_audio(path)
        temps = [audio_path] if is_temp else []
        try:
            with open(audio_path, "rb") as fh:
                # One byte past the limit is enough to know: a huge video is never loaded into memory.
                audio_bytes = fh.read(self._max_upload_bytes + 1)
            limit_mb = self._max_upload_bytes // (1024 * 1024)
            if len(audio_bytes) <= self._max_upload_bytes:
                pieces = [(audio_bytes, 0)]
                extracted = time.monotonic()
            elif not is_temp:
                # This is still the whole VIDEO: its audio could not be pulled out. Without ffmpeg that is the
                # usual reason, and it is a server fix, not something the teacher can do by trimming the video.
                raise ExternalSTTError(
                    f"The file is over the {limit_mb} MB upload limit and its audio could not be extracted.",
                    category="too_large", hint=None if _ffmpeg_path() else "no_ffmpeg")
            else:
                # A long lecture: the audio alone is over the limit, so send it in several pieces.
                split = _split_audio(audio_path, self._max_upload_bytes)
                temps += [p for p, _ in split]
                extracted = time.monotonic()
                pieces = []
                for piece_path, offset in split:
                    with open(piece_path, "rb") as fh:
                        pieces.append((fh.read(), offset))
            fields = {"model": self._model, "response_format": "verbose_json"}
            if language:
                fields["language"] = language
            # Groq's Cloudflare edge answers urllib's default User-Agent with 403 (error code 1010).
            headers = {"Authorization": f"Bearer {self._api_key}", "User-Agent": "Madar-Backend/1.0"}
            results = []
            for data, offset in pieces:
                call_started = time.monotonic()
                status, resp_headers, raw = self._transport(
                    self.API_URL, headers, fields, "audio.mp3", data, self._timeout)
                if status != 200:
                    err = self._error_for(status, resp_headers, raw)
                    err.elapsed_ms = _ms(time.monotonic() - call_started)
                    raise err
                results.append((self._parse(raw), offset))
            called = time.monotonic()
        finally:
            _remove_files(temps)
        result = self._merge(results)
        result["audio_bytes"] = sum(len(d) for d, _ in pieces)
        result["parts"] = len(pieces)
        result["timings_ms"] = {"audio_extract": _ms(extracted - started), "api_call": _ms(called - extracted),
                                "total": _ms(time.monotonic() - started)}
        return result

    @staticmethod
    def _merge(results):
        """One result from the per-piece results: texts joined in order, segment times moved to where the piece
        sits in the whole lecture. A single piece is returned unchanged."""
        if len(results) == 1:
            return results[0][0]
        text, segments, language, duration = [], [], "", 0.0
        for res, offset in results:
            if res["text"]:
                text.append(res["text"])
            language = language or res.get("language") or ""
            for seg in res["segments"]:
                segments.append({**seg, "start": round(seg["start"] + offset, 2), "end": round(seg["end"] + offset, 2)})
            if res.get("duration"):
                duration = max(duration, offset + float(res["duration"]))
        return {"text": " ".join(text), "language": language, "duration": duration or None, "segments": segments}

    def _error_for(self, status, headers, raw):
        message = _parse_groq_error(raw)
        safe = _redact(message, self._api_key)[:200]
        detail = f"Groq STT HTTP {status}" + (f": {safe}" if safe else "")
        if status in (401, 403):
            return ExternalSTTError(detail, category="auth", status=status)
        if status == 429:
            return ExternalSTTError(detail, category="rate_limit", status=status)
        if status == 413:
            return ExternalSTTError(detail, category="too_large", status=status)
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
    """FROZEN: not registered in `_TRANSCRIBERS` (see the module docstring).

    Primary: an external STT API. Falls back to a local transcriber when
    the primary is unconfigured, rate limited, times out, or is otherwise
    unavailable — so a lesson is never left untranscribed over a transient API
    problem. If the fallback also fails, its `TranscriptionError` (a safe,
    teacher-facing message) is what the caller sees."""
    name = "external_stt_with_fallback"

    def __init__(self, primary: Transcriber | None, fallback: Transcriber):
        self._primary = primary
        self._fallback = fallback

    def transcribe(self, path, language=""):
        reason, failed_after_ms = "", None
        if self._primary is None:
            reason = "groq_not_configured"
            log.warning("GROQ_API_KEY is not set: transcribing with the local %s model instead.", self._fallback.name)
        else:
            try:
                result = self._primary.transcribe(path, language)
                result.setdefault("provider", self._primary.name)
                return result
            except ExternalSTTError as exc:
                reason = f"{exc.category}" + (f":{exc.status}" if exc.status else "")
                failed_after_ms = exc.elapsed_ms
                log.warning(
                    "external STT failed (category=%s status=%s), falling back to %s: %s",
                    exc.category, exc.status, self._fallback.name, exc,
                )
            except Exception:
                reason = "unexpected_error"
                log.exception(
                    "external STT raised an unexpected error, falling back to %s", self._fallback.name)
        result = self._fallback.transcribe(path, language)
        result.setdefault("provider", self._fallback.name)
        result["fallback_reason"] = reason
        if failed_after_ms is not None:
            result.setdefault("timings_ms", {})["groq_failed_after"] = failed_after_ms
        return result


_TRANSCRIBERS = {
    GroqWhisperTranscriber.name: GroqWhisperTranscriber,
}

_STT_BUSY = "خدمة تحويل الفيديو إلى نص غير متاحة حاليًا. حاول مرة أخرى بعد قليل."
_STT_NOT_CONFIGURED = "خدمة تحويل الفيديو إلى نص غير مهيأة على الخادم. تواصل مع الدعم الفني."
# The video is too big to send as it is and the server has no ffmpeg to pull the audio out of it.
_STT_NO_FFMPEG = ("هذا الفيديو كبير، والخادم يفتقد أداة معالجة الصوت (ffmpeg) اللازمة لتصغيره قبل تحويله إلى نص. "
                  "تواصل مع الدعم الفني.")
_STT_FAILURE_MESSAGES = {
    "config": _STT_NOT_CONFIGURED, "auth": _STT_NOT_CONFIGURED,
    "rate_limit": "تم بلوغ الحد المسموح لخدمة تحويل الفيديو إلى نص. حاول مرة أخرى لاحقًا.",
    "too_large": "صوت هذا الفيديو أكبر من الحجم الذي تقبله خدمة تحويل الفيديو إلى نص.",
    "bad_request": "لم تقبل خدمة تحويل الفيديو إلى نص هذا الملف.",
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
    except ExternalSTTError as exc:
        log.warning("transcription failed transcript=%s category=%s status=%s hint=%s: %s",
                    transcript_id, exc.category, exc.status, exc.hint, exc)
        message = _STT_NO_FFMPEG if exc.hint == "no_ffmpeg" else _STT_FAILURE_MESSAGES.get(exc.category, _STT_BUSY)
        _fail(transcript_id, message)
        return
    except Exception:
        log.exception("transcription failed for transcript %s", transcript_id)
        _fail(transcript_id, "حدث خطأ غير متوقع أثناء تحويل الفيديو إلى نص.")
        return

    duration = result.get("duration")
    log.info(
        "transcription done transcript=%s provider=%s language=%s audio_s=%s chars=%s fallback_reason=%s timings_ms=%s",
        transcript_id, result.get("provider") or transcriber.name, result.get("language", ""),
        int(duration) if duration else None, len(text), result.get("fallback_reason") or "-",
        result.get("timings_ms"))
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
