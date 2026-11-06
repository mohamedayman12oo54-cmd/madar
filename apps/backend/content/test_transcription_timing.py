"""Timing capture + fallback reasons in the transcription layer, and the
`benchmark_pipeline` diagnostic command. No network: transports and providers
are fakes."""
import io
import json
import os
import tempfile
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings

from ai.providers import QuizResult
from . import transcription
from .management.commands import benchmark_pipeline as bp
from .transcription import (
    ExternalSTTError, FallbackTranscriber, GeminiTranscriber, Transcriber,
)

OK_BODY = {"text": "نص الدرس", "language": "ar", "duration": 60.0,
           "segments": [{"start": 0, "end": 2, "text": "نص الدرس"}]}


def _gemini_reply(status=200, error_status=""):
    if status != 200:
        return status, {}, json.dumps({"error": {"code": status, "message": "slow down", "status": error_status}}).encode()
    text = json.dumps({"language": "ar", "segments": [{"start": "00:00", "text": "نص الدرس"}]}, ensure_ascii=False)
    body = {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}],
            "usageMetadata": {"promptTokenCount": 10, "candidatesTokenCount": 5}}
    return 200, {}, json.dumps(body, ensure_ascii=False).encode()


def _gemini(status=200, error_status=""):
    def transport(url, headers, payload, timeout):
        return _gemini_reply(status, error_status)
    return GeminiTranscriber(api_key="unit-test-key", model="unit-test-model", transport=transport)


def _transcribe(client):
    fd, audio = tempfile.mkstemp(suffix=".mp3")
    os.write(fd, b"0123456789")
    os.close(fd)
    try:
        with mock.patch.object(transcription, "_extract_audio", return_value=(audio, False)):
            return client.transcribe("/tmp/video.mp4", "ar")
    finally:
        os.remove(audio)


class _Local(Transcriber):
    name = "faster_whisper"

    def transcribe(self, path, language=""):
        return {"text": "محلي", "language": "ar", "duration": 60.0, "segments": [],
                "timings_ms": {"model_load": 5, "decode": 50, "total": 55}}


@override_settings(LLM_MAX_RETRIES=0)
class GeminiTimingTests(SimpleTestCase):
    def test_success_reports_stage_timings_and_upload_size(self):
        result = _transcribe(_gemini())
        self.assertEqual(set(result["timings_ms"]), {"audio_extract", "api_call", "total"})
        self.assertTrue(all(isinstance(v, int) and v >= 0 for v in result["timings_ms"].values()))
        self.assertEqual(result["audio_bytes"], 10)

    def test_rate_limit_error_carries_how_long_the_call_took(self):
        with self.assertRaises(ExternalSTTError) as ctx:
            _transcribe(_gemini(429, "RESOURCE_EXHAUSTED"))
        self.assertEqual(ctx.exception.category, "rate_limit")
        self.assertIsInstance(ctx.exception.elapsed_ms, int)


class FallbackReasonTests(SimpleTestCase):
    def test_primary_success_has_no_fallback_reason(self):
        result = FallbackTranscriber(_Primary(), _Local()).transcribe("/tmp/v.mp4")
        self.assertEqual(result["provider"], "gemini_audio")
        self.assertNotIn("fallback_reason", result)

    def test_rate_limit_is_recorded_as_the_reason_and_local_text_is_used(self):
        primary = _Primary(ExternalSTTError("limit", category="rate_limit", status=429))
        primary_error = primary.error
        primary_error.elapsed_ms = 321
        result = FallbackTranscriber(primary, _Local()).transcribe("/tmp/v.mp4")
        self.assertEqual(result["provider"], "faster_whisper")
        self.assertEqual(result["text"], "محلي")
        self.assertEqual(result["fallback_reason"], "rate_limit:429")
        self.assertEqual(result["timings_ms"]["primary_failed_after"], 321)
        self.assertEqual(result["timings_ms"]["decode"], 50)

    def test_network_failure_has_a_category_only_reason(self):
        primary = _Primary(ExternalSTTError("down", category="network"))
        result = FallbackTranscriber(primary, _Local()).transcribe("/tmp/v.mp4")
        self.assertEqual(result["fallback_reason"], "network")

    def test_missing_key_is_no_longer_silent(self):
        with self.assertLogs("content.transcription", level="WARNING") as logs:
            result = FallbackTranscriber(None, _Local()).transcribe("/tmp/v.mp4")
        self.assertEqual(result["fallback_reason"], "primary_not_configured")
        self.assertIn("api_for_transcript is not set", logs.output[0])


class _Primary(Transcriber):
    name = "gemini_audio"

    def __init__(self, error=None):
        self.error = error

    def transcribe(self, path, language=""):
        if self.error:
            raise self.error
        return dict(OK_BODY, timings_ms={"total": 1})


class BenchmarkCommandTests(SimpleTestCase):
    def setUp(self):
        fd, self.video = tempfile.mkstemp(suffix=".mp4")
        os.write(fd, b"x" * 2048)
        os.close(fd)
        self.addCleanup(os.remove, self.video)
        self.primary_ok = dict(OK_BODY, text="نص الدرس " * 80, audio_bytes=480_000,
                            timings_ms={"audio_extract": 800, "api_call": 2400, "total": 3200})
        self.quiz = QuizResult(
            questions=[{"difficulty": d} for d in ["easy"] * 3 + ["medium"] * 3 + ["hard"] * 4],
            metadata={"timings_ms": {"generation": 7000, "content_check": 3000, "total": 7100},
                      "attempts": 1, "usage": {"total_tokens": 4321}, "source_chars": 640})

    def _run(self, *args, primary=None, quiz=None, quiz_error=None):
        out = io.StringIO()
        provider = mock.Mock()
        if quiz_error:
            provider.generate_quiz_result.side_effect = quiz_error
        else:
            provider.generate_quiz_result.return_value = quiz or self.quiz
        patches = [
            mock.patch.object(bp, "_media_seconds", return_value=60.0),
            mock.patch.object(GeminiTranscriber, "is_configured", return_value=True),
            mock.patch.object(bp, "LLMQuizProvider", **{"from_settings.return_value": provider}),
            mock.patch.object(bp, "QuizGenerationConfig"),
        ]
        if callable(primary):
            patches.append(mock.patch.object(GeminiTranscriber, "transcribe", new=primary))
        elif isinstance(primary, Exception):
            patches.append(mock.patch.object(GeminiTranscriber, "transcribe", side_effect=primary))
        else:
            patches.append(mock.patch.object(GeminiTranscriber, "transcribe", return_value=primary or self.primary_ok))
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        call_command("benchmark_pipeline", "--video", self.video, "--language", "ar", *args, stdout=out)
        return out.getvalue(), provider

    def test_full_report_has_every_stage_and_the_end_to_end_total(self):
        out, provider = self._run()
        for needle in ("PIPELINE TIMING REPORT", "Transcription - Gemini", "Audio extraction", "Gemini API call",
                       "Generation call", "Content check (parallel)", "10 questions", "END TO END"):
            self.assertIn(needle, out)
        self.assertIn("x real time", out)
        provider.generate_quiz_result.assert_called_once()

    def test_transcript_text_is_not_printed_unless_asked(self):
        out, _ = self._run()
        self.assertNotIn("نص الدرس", out)
        out, _ = self._run("--show-text")
        self.assertIn("Transcript start", out)

    def test_transcription_rate_limit_is_reported_and_quiz_is_skipped_not_crashed(self):
        out, provider = self._run(primary=ExternalSTTError("limit", category="rate_limit", status=429))
        self.assertIn("category=rate_limit status=429", out)
        self.assertIn("Quiz skipped", out)
        provider.generate_quiz_result.assert_not_called()

    def test_quiz_failure_is_reported_with_its_timing(self):
        from ai.quiz_generation import QuizGenerationError
        err = QuizGenerationError("insufficient_source", {"timings_ms": {"total": 10}})
        out, _ = self._run(quiz_error=err)
        self.assertIn("FAILED", out)
        self.assertIn("insufficient_source", out)

    def test_json_output_has_timings_and_no_lesson_text(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        os.close(fd)
        self.addCleanup(os.remove, path)
        self._run("--output", path)
        raw = open(path, encoding="utf-8").read()
        data = json.loads(raw)
        self.assertEqual(data["transcription"]["wall_ms"] >= 0, True)
        self.assertEqual(data["quiz"]["questions"], 10)
        self.assertNotIn("نص الدرس", raw)
