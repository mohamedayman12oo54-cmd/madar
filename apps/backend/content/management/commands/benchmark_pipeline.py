"""
Times the REAL lesson pipeline end to end on one video and prints a report:

    1. Groq Whisper (the only transcriber)            -> extract / API / total time
    2. Gemini quiz generation from the transcript     -> generation / content check / total

    python manage.py benchmark_pipeline --video "E:\\lessons\\lesson1.mp4" --language ar
    python manage.py benchmark_pipeline --item 12 --language ar
    python manage.py benchmark_pipeline --video lesson.mp4 --language ar --no-quiz

It is a diagnostic, not part of the product or the test suite. It SENDS the
video's audio to Groq and the transcript to Gemini (it needs GROQ_API_KEY and
the Gemini settings), so use a lesson you are allowed to send. Nothing is
written to the database. The transcript and the questions are never printed or
saved unless you pass --show-text / --output.
"""
import json
import subprocess
import time
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from ai.llm import LLMError
from ai.providers import AIProviderError
from ai.quiz_contract import QuizConfigError, QuizGenerationConfig
from ai.quiz_generation import LLMQuizProvider
from content.models import ContentItem
from content.transcription import ExternalSTTError, GroqWhisperTranscriber


def _fmt_ms(ms):
    if ms is None:
        return "-"
    return f"{ms / 1000:.1f}s ({ms} ms)"


def _media_seconds(path):
    """Duration from ffprobe, or None when ffprobe is unavailable."""
    try:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", path],
            capture_output=True, text=True, timeout=60, check=False)
        return float(out.stdout.strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


class Command(BaseCommand):
    help = "Time Groq transcription and Gemini quiz generation on one video."

    def add_arguments(self, parser):
        src = parser.add_mutually_exclusive_group(required=True)
        src.add_argument("--video", help="Path to a video/audio file on this machine.")
        src.add_argument("--item", type=int, help="ContentItem id whose uploaded video to use.")
        parser.add_argument("--language", default=None,
                            help="Spoken language code, e.g. ar (default: TRANSCRIPTION_LANGUAGE).")
        parser.add_argument("--no-quiz", action="store_true", help="Skip the Gemini quiz step.")
        parser.add_argument("--title", default="", help="Lesson title for the quiz (default: file name).")
        parser.add_argument("--show-text", action="store_true", help="Print the first 300 characters of the transcript.")
        parser.add_argument("--output", default="", help="Write the timing report (no lesson text) as JSON here.")

    # ------------------------------------------------------------------ run --
    def handle(self, *args, **opts):
        path = self._resolve_path(opts)
        language = opts["language"]
        if language is None:
            language = getattr(settings, "TRANSCRIPTION_LANGUAGE", "")
        title = opts["title"] or Path(path).stem
        report = {"file": Path(path).name, "language": language or "auto-detect"}
        audio_s = _media_seconds(path)
        report["media_seconds"] = round(audio_s, 1) if audio_s else None
        size_mb = Path(path).stat().st_size / 1_000_000
        report["file_mb"] = round(size_mb, 1)
        self.stdout.write(f"File: {Path(path).name}  {size_mb:.1f} MB  "
                          f"{'%.0f s of media' % audio_s if audio_s else 'duration unknown (no ffprobe)'}  "
                          f"language={language or 'auto-detect'}")

        text = self._step_groq(path, language, report)

        if opts["show_text"] and text:
            self.stdout.write("\nTranscript start: " + text[:300].replace("\n", " "))

        if opts["no_quiz"]:
            report["quiz"] = {"status": "skipped"}
        elif not text:
            report["quiz"] = {"status": "skipped", "reason": "no transcript"}
            self.stdout.write(self.style.WARNING("Quiz skipped: there is no transcript to build it from."))
        else:
            self._step_quiz(title, text, report)

        self._print_report(report)
        if opts["output"]:
            Path(opts["output"]).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(f"\nJSON report written to {opts['output']}")

    def _resolve_path(self, opts):
        if opts["video"]:
            p = Path(opts["video"])
            if not p.is_file():
                raise CommandError(f"File not found: {p}")
            return str(p)
        try:
            item = ContentItem.objects.get(pk=opts["item"])
        except ContentItem.DoesNotExist:
            raise CommandError(f"No ContentItem with id {opts['item']}.") from None
        if not item.video_file:
            raise CommandError(f"ContentItem {item.pk} has no uploaded video.")
        return item.video_file.path

    # ---------------------------------------------------------------- steps --
    def _step_groq(self, path, language, report):
        self.stdout.write("\n[1/2] Groq Whisper ...")
        if not GroqWhisperTranscriber.is_configured():
            report["groq"] = {"status": "not_configured"}
            self.stdout.write(self.style.ERROR("GROQ_API_KEY is not set, so the app cannot transcribe anything."))
            return ""
        started = time.monotonic()
        try:
            result = GroqWhisperTranscriber().transcribe(path, language)
        except ExternalSTTError as exc:
            wall = int((time.monotonic() - started) * 1000)
            report["groq"] = {"status": "failed", "category": exc.category, "http_status": exc.status, "wall_ms": wall}
            self.stdout.write(self.style.ERROR(
                f"FAILED after {_fmt_ms(wall)}: category={exc.category} status={exc.status} - {exc}"))
            return ""
        wall = int((time.monotonic() - started) * 1000)
        text = result["text"]
        report["groq"] = {
            "status": "ok", "model": GroqWhisperTranscriber().__dict__.get("_model"), "wall_ms": wall,
            "timings_ms": result.get("timings_ms"), "audio_uploaded_mb": round(result.get("audio_bytes", 0) / 1e6, 2),
            "detected_language": result.get("language"), "chars": len(text), "segments": len(result["segments"]),
        }
        self.stdout.write(self.style.SUCCESS(f"OK in {_fmt_ms(wall)}  language={result.get('language')}  chars={len(text)}"))
        return text

    def _step_quiz(self, title, text, report):
        self.stdout.write("\n[2/2] Gemini quiz generation ...")
        try:
            QuizGenerationConfig.from_settings()   # fail early, with the setting's name, on a bad configuration
        except QuizConfigError as exc:
            report["quiz"] = {"status": "config_error", "error": str(exc)}
            self.stdout.write(self.style.ERROR(f"Quiz settings problem: {exc}"))
            return
        provider = LLMQuizProvider.from_settings()   # exactly how the product builds it (parallel check, sampling)
        started = time.monotonic()
        try:
            result = provider.generate_quiz_result({"title": title, "text": text})
        except AIProviderError as exc:
            wall = int((time.monotonic() - started) * 1000)
            meta = getattr(exc, "metadata", {}) or {}
            report["quiz"] = {"status": "failed", "category": getattr(exc, "category", "unexpected"),
                              "wall_ms": wall, "timings_ms": meta.get("timings_ms")}
            self.stdout.write(self.style.ERROR(f"FAILED after {_fmt_ms(wall)}: [{report['quiz']['category']}]"))
            return
        except LLMError as exc:
            raise CommandError(f"[{exc.category}] {exc}") from None
        wall = int((time.monotonic() - started) * 1000)
        meta = result.metadata
        usage = meta.get("usage", {}) or {}
        by_level = {}
        for q in result.questions:
            lvl = q.get("difficulty") if isinstance(q, dict) else None
            by_level[lvl] = by_level.get(lvl, 0) + 1
        report["quiz"] = {
            "status": "ok", "wall_ms": wall, "timings_ms": meta.get("timings_ms"), "attempts": meta.get("attempts"),
            "questions": len(result.questions), "by_difficulty": by_level, "tokens": usage.get("total_tokens"),
            "source_chars": meta.get("source_chars"), "model": getattr(settings, "GEMINI_MODEL", ""),
        }
        self.stdout.write(self.style.SUCCESS(f"OK in {_fmt_ms(wall)}  questions={len(result.questions)}"))

    # --------------------------------------------------------------- report --
    def _print_report(self, r):
        w = self.stdout.write
        w("\n" + "=" * 62)
        w("PIPELINE TIMING REPORT")
        w("=" * 62)
        w(f"Video          : {r['file']}  ({r['file_mb']} MB, "
          f"{('%.0f s' % r['media_seconds']) if r['media_seconds'] else 'duration unknown'})")
        w(f"Language       : {r['language']}")

        g = r.get("groq", {})
        w("\n1) Transcription - Groq Whisper")
        if g.get("status") == "ok":
            t = g["timings_ms"] or {}
            w(f"   Audio extraction (ffmpeg) : {_fmt_ms(t.get('audio_extract'))}")
            w(f"   Groq API call             : {_fmt_ms(t.get('api_call'))}   (uploaded {g['audio_uploaded_mb']} MB)")
            w(f"   TOTAL                     : {_fmt_ms(g['wall_ms'])}")
            if r["media_seconds"]:
                w(f"   Speed                     : {r['media_seconds'] / (max(g['wall_ms'], 1) / 1000):.1f}x real time "
                  "(10x = a 10-minute video in 1 minute)")
            w(f"   Result                    : language={g['detected_language']}, {g['chars']} chars, {g['segments']} segments")
        else:
            w(f"   NOT MEASURED: {g.get('status')} {g.get('category', '')} {g.get('http_status') or ''}")

        q = r.get("quiz", {})
        w("\n2) Quiz generation - Gemini")
        if q.get("status") == "ok":
            t = q["timings_ms"] or {}
            for key, label in (("generation", "Generation call"), ("content_check", "Content check (parallel)"),
                               ("total", "Pipeline total")):
                if key in t:
                    w(f"   {label:<26}: {_fmt_ms(t[key])}")
            w(f"   TOTAL (wall clock)        : {_fmt_ms(q['wall_ms'])}")
            w(f"   Model                     : {q.get('model') or '-'}")
            w(f"   Result                    : {q['questions']} questions {q['by_difficulty']}, "
              f"attempts={q['attempts']}, tokens={q['tokens']}, source={q['source_chars']} chars")
        else:
            w(f"   NOT MEASURED: {q.get('status')} {q.get('category') or q.get('reason') or q.get('error') or ''}")

        if g.get("status") == "ok" and q.get("status") == "ok":
            total = g["wall_ms"] + q["wall_ms"]
            w(f"\nEND TO END (video -> quiz ready): {_fmt_ms(total)}")
        w("=" * 62)
