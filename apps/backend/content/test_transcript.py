"""Pipeline step 2: an uploaded lesson video gets a persisted, timestamped
transcript the teacher can read (the quiz steps build on it later)."""
import json
from unittest import mock

from django.test import SimpleTestCase, override_settings

from . import transcription
from .models import Transcript
from .test_video import _Base, video
from .transcription import (
    ExternalSTTError, FallbackTranscriber, GroqWhisperTranscriber, Transcriber,
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


class GroqWhisperTranscriberTests(SimpleTestCase):
    """The external-API adapter: request shape and HTTP-status -> category
    mapping, independent of the fallback decision (tested separately below)."""

    def _client(self, status, body, transport_error=None):
        def fake_transport(url, headers, fields, filename, file_bytes, timeout):
            if transport_error:
                raise transport_error
            return status, {}, json.dumps(body).encode()
        return GroqWhisperTranscriber(api_key="gsk_test", model="whisper-large-v3-turbo", transport=fake_transport)

    def test_success_parses_text_language_and_segments(self):
        client = self._client(200, {
            "text": " hello world ", "language": "en", "duration": 12.5,
            "segments": [{"start": 0, "end": 1.2, "text": " hello "}, {"start": 1.2, "end": 2.0, "text": "world"}],
        })
        with mock.patch.object(transcription, "_extract_audio", return_value=("/tmp/x.mp3", False)), \
                mock.patch("builtins.open", mock.mock_open(read_data=b"fake-audio")):
            result = client.transcribe("/tmp/video.mp4", "en")
        self.assertEqual(result["text"], "hello world")
        self.assertEqual(result["language"], "en")
        self.assertEqual(result["duration"], 12.5)
        self.assertEqual(len(result["segments"]), 2)

    def test_rate_limit_is_categorised_for_the_fallback_decision(self):
        client = self._client(429, {"error": {"message": "Rate limit exceeded"}})
        with mock.patch.object(transcription, "_extract_audio", return_value=("/tmp/x.mp3", False)), \
                mock.patch("builtins.open", mock.mock_open(read_data=b"fake-audio")):
            with self.assertRaises(ExternalSTTError) as ctx:
                client.transcribe("/tmp/video.mp4")
        self.assertEqual(ctx.exception.category, "rate_limit")
        self.assertEqual(ctx.exception.status, 429)

    def test_server_error_is_categorised_as_provider(self):
        client = self._client(503, {"error": {"message": "Service unavailable"}})
        with mock.patch.object(transcription, "_extract_audio", return_value=("/tmp/x.mp3", False)), \
                mock.patch("builtins.open", mock.mock_open(read_data=b"fake-audio")):
            with self.assertRaises(ExternalSTTError) as ctx:
                client.transcribe("/tmp/video.mp4")
        self.assertEqual(ctx.exception.category, "provider")

    def test_auth_failure_never_leaks_the_api_key_into_the_message(self):
        client = self._client(401, {"error": {"message": "Invalid API Key: gsk_test"}})
        with mock.patch.object(transcription, "_extract_audio", return_value=("/tmp/x.mp3", False)), \
                mock.patch("builtins.open", mock.mock_open(read_data=b"fake-audio")):
            with self.assertRaises(ExternalSTTError) as ctx:
                client.transcribe("/tmp/video.mp4")
        self.assertEqual(ctx.exception.category, "auth")
        self.assertNotIn("gsk_test", str(ctx.exception))

    def test_unset_api_key_raises_a_config_error_without_any_network_call(self):
        client = GroqWhisperTranscriber(api_key="", transport=mock.Mock(side_effect=AssertionError("called")))
        with self.assertRaises(ExternalSTTError) as ctx:
            client.transcribe("/tmp/video.mp4")
        self.assertEqual(ctx.exception.category, "config")


class FallbackTranscriberTests(SimpleTestCase):
    """The chain: external API first, local transcriber only when the
    primary is unavailable — this is the behaviour requested in the task."""

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
    def test_default_provider_is_the_external_api_with_local_fallback(self):
        transcriber = transcription.get_transcriber()
        self.assertIsInstance(transcriber, FallbackTranscriber)

    @override_settings(TRANSCRIPTION_PROVIDER="faster_whisper")
    def test_can_be_pinned_to_local_only(self):
        transcriber = transcription.get_transcriber()
        self.assertEqual(transcriber.name, "faster_whisper")

    @override_settings(GROQ_API_KEY="gsk_configured")
    def test_primary_is_built_only_when_an_api_key_is_configured(self):
        transcriber = transcription.get_transcriber()
        self.assertIsNotNone(transcriber._primary)

    def test_primary_is_none_without_an_api_key(self):
        transcriber = transcription.get_transcriber()
        self.assertIsNone(transcriber._primary)


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
        with mock.patch.dict(transcription._TRANSCRIBERS, {"faster_whisper": FakeTranscriber}):
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
        with mock.patch.dict(transcription._TRANSCRIBERS, {"faster_whisper": BrokenTranscriber}):
            run_transcription(row.pk)
        body = self.get().json()
        self.assertEqual((body["status"], body["text"]), ("failed", ""))
        self.assertTrue(body["error"])
        self.assertEqual(self.post().json()["status"], "pending")

    def test_replacing_the_video_discards_the_old_text(self):
        self.upload()
        row = Transcript.objects.get(item=self.item)
        with mock.patch.dict(transcription._TRANSCRIBERS, {"faster_whisper": FakeTranscriber}):
            run_transcription(row.pk)
        self.upload()
        body = self.get().json()
        self.assertEqual((body["status"], body["text"]), ("pending", ""))

    def test_removing_the_video_removes_the_transcript(self):
        self.upload()
        r = self.client_a.delete(f"/api/v1/content/{self.item.id}/video/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Transcript.objects.filter(item=self.item).exists())

    def test_missing_library_gives_an_actionable_message(self):
        self.upload()
        row = Transcript.objects.get(item=self.item)
        with mock.patch.dict("sys.modules", {"faster_whisper": None}):
            run_transcription(row.pk)
        row.refresh_from_db()
        self.assertEqual(row.status, "failed")
        self.assertIn("faster-whisper", row.error)

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
