"""Pipeline step 2: an uploaded lesson video gets a persisted, timestamped
transcript the teacher can read (the quiz steps build on it later)."""
from unittest import mock

from django.test import override_settings

from . import transcription
from .models import Transcript
from .test_video import _Base, video
from .transcription import Transcriber, TranscriptionError, run_transcription


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
