"""Quiz requests use the COMPLETE lesson material: the stored transcript for an
uploaded video, the teacher's full text otherwise — and fail explicitly (never
silently fall back to partial content) when the transcript is not usable.
Authorisation, ownership and quiz validation stay exactly as before."""
from unittest import mock

from django.core.management import call_command
from django.utils import timezone

from ai.models import AIOperation
from ai.providers import AIProvider, AIProviderError
from content.models import ContentItem, Transcript

from .models import Quiz
from .tests import LESSON, Base


def lesson_text(sentences=2500):
    """~2 hours of speech: each sentence is numbered so truncation is visible."""
    return " ".join(f"الجملة رقم {i} تشرح جزءًا من درس الخلية والبناء الضوئي." for i in range(1, sentences + 1))


class RecordingProvider(AIProvider):
    """Stands in for a real model: records exactly what the worker hands it."""

    def __init__(self):
        self.calls = []

    def generate_quiz(self, title, text):
        self.calls.append((title, text))
        return [{"q": "سؤال؟", "options": ["أ", "ب"], "answer_index": 0, "explanation": ""}]


class TranscriptQuizBase(Base):
    def uploaded(self, status=Transcript.Status.COMPLETED, text=None, target=True, **kw):
        item = self.video(source=ContentItem.Source.UPLOAD, video_provider="none", video_ref="", **kw)
        if target:
            item.target_grades.add(self.grade)
        if status is not None:
            Transcript.objects.create(
                environment=self.env_a, item=item, status=status,
                text=lesson_text() if text is None else text, language="ar", duration_seconds=7200,
                segments=[{"start": 0.0, "end": 2.5, "text": "الجملة رقم 1"}], provider="faster_whisper")
        return item

    def request(self, item, **kw):
        return self.post("quizzes/", {"content_id": item.id, **kw})


class LongTranscriptTests(TranscriptQuizBase):
    def test_the_whole_transcript_is_snapshotted_not_a_6000_char_prefix(self):
        item = self.uploaded(description="", quiz_source="")
        full = Transcript.objects.get(item=item).text
        self.assertGreater(len(full), 100_000)

        r = self.request(item)
        self.assertEqual(r.status_code, 202, r.content)
        evidence = AIOperation.objects.get(pk=r.json()["id"]).evidence
        self.assertEqual(evidence["text"], full)
        self.assertIn("الجملة رقم 2500 ", evidence["text"])           # the last minute of the lesson
        self.assertEqual(evidence["source"]["origin"], "transcript")
        self.assertEqual(evidence["source"]["char_count"], len(full))
        self.assertEqual(evidence["source"]["transcript_id"], Transcript.objects.get(item=item).pk)

    def test_the_worker_hands_the_provider_the_complete_text(self):
        item = self.uploaded(description="", quiz_source="")
        full = Transcript.objects.get(item=item).text
        self.assertEqual(self.request(item).status_code, 202)

        provider = RecordingProvider()
        with mock.patch("ai.management.commands.process_ai_operations.get_provider", return_value=provider):
            call_command("process_ai_operations")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(provider.calls[0], ("درس الخلية", full))
        self.assertEqual(Quiz.objects.count(), 1)

    def test_the_default_provider_still_produces_a_valid_quiz_from_a_long_transcript(self):
        item = self.uploaded(description="", quiz_source="")
        op_id = self.request(item).json()["id"]
        call_command("process_ai_operations")
        op = self.get(f"quizzes/operations/{op_id}/").json()
        self.assertEqual((op["status"], bool(op["quiz_id"])), ("completed", True))

    def test_the_stored_transcript_is_not_modified_by_a_quiz_request(self):
        item = self.uploaded()
        before = Transcript.objects.values().get(item=item)
        self.request(item)
        call_command("process_ai_operations")
        self.assertEqual(Transcript.objects.values().get(item=item), before)

    def test_teacher_text_is_no_longer_sliced_for_external_videos(self):
        body = "جملة من شرح المعلم عن الخلية. " * 1000                  # ~30k chars
        item = self.video(description=body, quiz_source="")
        item.target_grades.add(self.grade)
        r = self.request(item)
        self.assertEqual(r.status_code, 202, r.content)
        evidence = AIOperation.objects.get(pk=r.json()["id"]).evidence
        self.assertEqual(evidence["text"], body.strip())
        self.assertEqual(evidence["source"]["origin"], "teacher_text")

    def test_student_visible_payloads_never_contain_the_transcript(self):
        item = self.uploaded()
        marker = "الجملة رقم 1250 "
        op = self.request(item).json()
        call_command("process_ai_operations")
        for path in ("videos/", "overview/", f"quizzes/operations/{op['id']}/", "quizzes/"):
            self.assertNotIn(marker, self.get(path).content.decode(), path)


class UnusableTranscriptTests(TranscriptQuizBase):
    def assert_refused(self, item, code):
        before = AIOperation.objects.count()
        r = self.request(item)
        self.assertEqual((r.status_code, r.json()["code"]), (409, code), r.content)
        self.assertTrue(r.json()["detail"])
        self.assertEqual(AIOperation.objects.count(), before)        # nothing was queued
        self.assertEqual(Quiz.objects.count(), 0)

    def test_pending_and_processing_say_try_again_later(self):
        for status in (Transcript.Status.PENDING, Transcript.Status.PROCESSING):
            with self.subTest(status=status):
                self.assert_refused(self.uploaded(status=status, text="", description=LESSON, quiz_source=LESSON),
                                    "transcript_not_ready")

    def test_failed_empty_or_missing_transcript_is_unavailable(self):
        self.assert_refused(self.uploaded(status=Transcript.Status.FAILED, text="", description=LESSON), "transcript_unavailable")
        self.assert_refused(self.uploaded(text="  ", description=LESSON), "transcript_unavailable")
        self.assert_refused(self.uploaded(status=None, description=LESSON, quiz_source=LESSON), "transcript_unavailable")

    def test_idempotent_replay_still_returns_the_existing_operation(self):
        item = self.uploaded()
        first = self.request(item, idempotency_key="k1")
        Transcript.objects.filter(item=item).update(status=Transcript.Status.FAILED)
        again = self.request(item, idempotency_key="k1")
        self.assertEqual((first.status_code, again.status_code), (202, 200))
        self.assertEqual(first.json()["id"], again.json()["id"])


class CanQuizFlagTests(TranscriptQuizBase):
    def can_quiz(self, item):
        rows = self.get("videos/").json()["results"]
        return next(r["can_quiz"] for r in rows if r["id"] == item.id)

    def test_uploaded_video_with_a_completed_transcript_can_be_quizzed_without_any_teacher_text(self):
        self.assertTrue(self.can_quiz(self.uploaded(description="", quiz_source="")))

    def test_uploaded_video_without_a_usable_transcript_cannot(self):
        for status, text in ((Transcript.Status.PENDING, ""), (Transcript.Status.FAILED, ""), (None, "")):
            with self.subTest(status=status):
                item = self.uploaded(status=status, text=text, description=LESSON, quiz_source=LESSON)
                self.assertFalse(self.can_quiz(item))

    def test_external_videos_keep_the_teacher_text_rule(self):
        ok = self.video(quiz_source=LESSON)
        ok.target_grades.add(self.grade)
        short = self.video(title="ق", description="قصير", quiz_source="")
        short.target_grades.add(self.grade)
        self.assertTrue(self.can_quiz(ok))
        self.assertFalse(self.can_quiz(short))

    def test_listing_does_not_query_once_per_video(self):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def queries():
            with CaptureQueriesContext(connection) as ctx:
                self.assertEqual(self.get("videos/").status_code, 200)
            return len(ctx)

        self.uploaded(description="", quiz_source="")
        one = queries()
        for _ in range(5):
            self.uploaded(description="", quiz_source="")
        self.assertEqual(queries(), one)


class AuthorizationUnchangedTests(TranscriptQuizBase):
    def test_unpublished_or_untargeted_uploaded_lessons_are_still_404(self):
        hidden = self.uploaded(target=False)
        draft = self.uploaded(published_at=None)
        for item in (hidden, draft):
            self.assertEqual(self.request(item).status_code, 404)
        self.assertEqual(AIOperation.objects.count(), 0)

    def test_another_environments_lesson_is_404(self):
        foreign = ContentItem.objects.create(
            environment=self.env_b, title="ب", source=ContentItem.Source.UPLOAD, published_at=timezone.now())
        Transcript.objects.create(environment=self.env_b, item=foreign, status=Transcript.Status.COMPLETED, text=lesson_text(5))
        self.assertEqual(self.request(foreign).status_code, 404)

    def test_a_teacher_still_cannot_use_the_student_quiz_endpoint(self):
        item = self.uploaded()
        r = self.client_a.post(f"/api/v1/student/quizzes/", {"content_id": item.id}, format="json", **self.with_env(self.env_a.id))
        self.assertIn(r.status_code, (403, 404))

    def test_provider_failure_still_leaves_no_quiz(self):
        item = self.uploaded()
        op_id = self.request(item).json()["id"]

        class Boom(AIProvider):
            def generate_quiz(self, title, text):
                raise AIProviderError("upstream unavailable")

        with mock.patch("ai.management.commands.process_ai_operations.get_provider", return_value=Boom()):
            call_command("process_ai_operations")
        op = self.get(f"quizzes/operations/{op_id}/").json()
        self.assertEqual((op["status"], op["quiz_id"]), ("failed", None))
        self.assertEqual(Quiz.objects.count(), 0)
