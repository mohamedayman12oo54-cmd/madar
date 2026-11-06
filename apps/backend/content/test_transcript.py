"""Pipeline step 2: an uploaded lesson video gets a persisted, timestamped
transcript the teacher can read (the quiz steps build on it later)."""
import json
from unittest import mock

from django.test import SimpleTestCase, override_settings

from . import transcription
from .models import Transcript
from .test_video import _Base, video
from .transcription import (
    ExternalSTTError, FallbackTranscriber, FasterWhisperTranscriber, GeminiTranscriber, Transcriber,
    TranscriptionError, run_transcription,
)


class FakeTranscriber(Transcriber):
    name = "fake"

    def transcribe(self, path, language=""):
        return {
            "text": "اليوم سنتعلم الجمع. الجمع هو ضم عددين.", "language": "ar", "duration": 95.4,
            "segments": [{"start": 0.0, "end": 3.1, "text": "اليوم سنتعلم الجمع."},
                         {"start": 3.1, "end": 6.0, "text": "الجمع هو ضم عددين."}],
        }


class BrokenTranscriber(Transcriber):
    name = "broken"

    def transcribe(self, path, language=""):
        raise TranscriptionError("تعذّر قراءة الصوت من ملف الفيديو.")


def url(pk):
    return f"/api/v1/content/{pk}/transcript/"


class FallbackTranscriberTests(SimpleTestCase):
    """FROZEN with faster-whisper: the chain stays correct for when it is
    registered again, but the product does not use it (GetTranscriberTests)."""

    def test_primary_success_is_used_as_is(self):
        primary, fallback = FakeTranscriber(), BrokenTranscriber()
        result = FallbackTranscriber(primary, fallback).transcribe("/tmp/video.mp4")
        self.assertEqual(result["provider"], "fake")

    def test_rate_limited_primary_falls_back_to_local_transcriber(self):
        class RateLimited(Transcriber):
            name = "rate_limited"

            def transcribe(self, path, language=""):
                raise ExternalSTTError("rate limited", category="rate_limit", status=429)

        result = FallbackTranscriber(RateLimited(), FakeTranscriber()).transcribe("/tmp/video.mp4")
        self.assertEqual(result["provider"], "fake")
        self.assertIn("الجمع", result["text"])

    def test_primary_timeout_falls_back(self):
        class TimedOut(Transcriber):
            name = "timed_out"

            def transcribe(self, path, language=""):
                raise ExternalSTTError("timed out", category="timeout")

        result = FallbackTranscriber(TimedOut(), FakeTranscriber()).transcribe("/tmp/video.mp4")
        self.assertEqual(result["provider"], "fake")

    def test_no_primary_configured_goes_straight_to_fallback(self):
        result = FallbackTranscriber(None, FakeTranscriber()).transcribe("/tmp/video.mp4")
        self.assertEqual(result["provider"], "fake")

    def test_both_failing_raises_the_fallback_s_clear_error(self):
        class Broken(Transcriber):
            name = "broken_primary"

            def transcribe(self, path, language=""):
                raise ExternalSTTError("boom", category="provider")

        with self.assertRaises(TranscriptionError) as ctx:
            FallbackTranscriber(Broken(), BrokenTranscriber()).transcribe("/tmp/video.mp4")
        self.assertEqual(str(ctx.exception), "تعذّر قراءة الصوت من ملف الفيديو.")


class GetTranscriberTests(SimpleTestCase):
    def test_default_provider_is_gemini_audio_alone(self):
        self.assertIs(type(transcription.get_transcriber()), GeminiTranscriber)

    def test_gemini_audio_is_the_only_registered_provider(self):
        self.assertEqual(list(transcription._TRANSCRIBERS), ["gemini_audio"])

    @override_settings(TRANSCRIPTION_PROVIDER="faster_whisper")
    def test_frozen_local_provider_cannot_be_selected(self):
        with self.assertRaises(TranscriptionError):
            transcription.get_transcriber()


@override_settings(TRANSCRIPTION_BACKGROUND="worker")  # no thread: tests run the worker step by hand
class TranscriptTests(_Base):
    def get(self, client=None, env=None, pk=None):
        return (client or self.client_a).get(url(pk or self.item.id), **self.with_env((env or self.env_a).id))

    def post(self, client=None, env=None, pk=None):
        return (client or self.client_a).post(url(pk or self.item.id), **self.with_env((env or self.env_a).id))

    def test_no_video_means_no_transcript(self):
        self.assertEqual(self.get().json()["status"], "none")
        self.assertEqual(self.post().status_code, 400)

    def test_uploading_a_video_queues_a_transcript(self):
        self.assertEqual(self.upload().status_code, 200)
        body = self.get().json()
        self.assertEqual((body["status"], body["text"]), ("pending", ""))

    def test_worker_completes_it_with_text_and_timestamps(self):
        self.upload()
        row = Transcript.objects.get(item=self.item)
        with mock.patch.dict(transcription._TRANSCRIBERS, {"gemini_audio": FakeTranscriber}):
            run_transcription(row.pk)
        body = self.get().json()
        self.assertEqual(body["status"], "completed")
        self.assertIn("الجمع", body["text"])
        self.assertEqual(body["language"], "ar")
        self.assertEqual(body["duration_seconds"], 95)
        self.assertEqual(len(body["segments"]), 2)
        self.assertEqual(body["word_count"], 7)

    def test_failure_is_explicit_and_retryable(self):
        self.upload()
        row = Transcript.objects.get(item=self.item)
        with mock.patch.dict(transcription._TRANSCRIBERS, {"gemini_audio": BrokenTranscriber}):
            run_transcription(row.pk)
        body = self.get().json()
        self.assertEqual((body["status"], body["text"]), ("failed", ""))
        self.assertTrue(body["error"])
        self.assertEqual(self.post().json()["status"], "pending")

    def test_replacing_the_video_discards_the_old_text(self):
        self.upload()
        row = Transcript.objects.get(item=self.item)
        with mock.patch.dict(transcription._TRANSCRIBERS, {"gemini_audio": FakeTranscriber}):
            run_transcription(row.pk)
        self.upload()
        body = self.get().json()
        self.assertEqual((body["status"], body["text"]), ("pending", ""))

    def test_removing_the_video_removes_the_transcript(self):
        self.upload()
        r = self.client_a.delete(f"/api/v1/content/{self.item.id}/video/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Transcript.objects.filter(item=self.item).exists())

    def _fail_with(self, category, status=None):
        self.upload()
        row = Transcript.objects.get(item=self.item)

        class Failing(Transcriber):
            name = "gemini_audio"

            def transcribe(self, path, language=""):
                raise ExternalSTTError("boom leaky_secret_value", category=category, status=status)

        with mock.patch.dict(transcription._TRANSCRIBERS, {"gemini_audio": Failing}), \
                mock.patch.object(FasterWhisperTranscriber, "transcribe",
                                  side_effect=AssertionError("the frozen local model ran")):
            run_transcription(row.pk)
        row.refresh_from_db()
        return row

    def test_rate_limit_fails_the_row_without_touching_the_local_model(self):
        row = self._fail_with("rate_limit", 429)
        self.assertEqual((row.status, row.text), ("failed", ""))
        self.assertEqual(row.error, transcription._STT_FAILURE_MESSAGES["rate_limit"])
        self.assertEqual(self.post().json()["status"], "pending")

    def test_every_failure_category_shows_a_safe_message(self):
        for category in ("config", "auth", "no_ffmpeg", "extract_failed", "split_failed", "provider_413",
                         "rate_limit", "bad_request", "timeout", "network", "provider", "malformed_response",
                         "blocked", "truncated"):
            with self.subTest(category=category):
                row = self._fail_with(category)
                self.assertEqual(row.status, "failed")
                self.assertTrue(row.error)
                self.assertNotIn("boom", row.error)
                self.assertNotIn("leaky_secret_value", row.error)

    def test_missing_api_key_fails_with_an_actionable_message(self):
        self.upload()
        row = Transcript.objects.get(item=self.item)
        run_transcription(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, "failed")
        self.assertEqual(row.error, transcription._STT_FAILURE_MESSAGES["config"])

    def test_another_teacher_cannot_read_it(self):
        self.upload()
        self.assertEqual(self.get(client=self.client_b, env=self.env_b).status_code, 404)
        self.assertEqual(self.post(client=self.client_b, env=self.env_b).status_code, 404)

    def test_students_cannot_read_it(self):
        self.upload()
        r = self.student_client().get(url(self.item.id), **self.with_env(self.env_a.id))
        self.assertIn(r.status_code, (403, 404))

    def test_list_exposes_the_status_only(self):
        self.upload()
        r = self.client_a.get("/api/v1/content/", **self.with_env(self.env_a.id))
        rows = r.json()["results"] if isinstance(r.json(), dict) else r.json()
        self.assertEqual(rows[0]["transcript_status"], "pending")
        self.assertNotIn("text", rows[0])  # the (long) text is only served by the transcript endpoint
