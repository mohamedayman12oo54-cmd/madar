"""End-to-end: student quiz request -> prepared transcript -> prompt -> (fake)
LLM -> deterministic validation -> persisted Quiz, through the REAL endpoint and
the REAL `process_ai_operations` worker with AI_PROVIDER=llm.

Only the model is faked. These tests prove the plumbing and the enforceable
contract; they do not prove the questions are good (see ai/quiz_evaluation.py)."""
import json
from unittest import mock

from django.core.management import call_command
from django.test import override_settings

from ai.llm import LLMRateLimitError, LLMTimeoutError
from ai.models import AIOperation
from ai.quiz_prompt import PROMPT_VERSION
from ai.test_quiz_generation import FakeClient, quiz_payload, reply
from content.models import Transcript

from .models import Quiz
from .test_quiz_transcript import TranscriptQuizBase, lesson_text

LLM = dict(AI_PROVIDER="llm", QUIZ_LANGUAGE="ar-msa", QUIZ_CONTENT_VALIDATION_ENABLED=False)


def run_worker(client):
    with mock.patch("ai.quiz_generation.get_llm_client", return_value=client):
        call_command("process_ai_operations")


@override_settings(**LLM)
class GenerationPipelineTests(TranscriptQuizBase):
    def request(self, item, **kw):
        r = super().request(item, **kw)
        self.assertIn(r.status_code, (200, 202), r.content)
        return r.json()["id"]

    def operation(self, op_id):
        return self.get(f"quizzes/operations/{op_id}/").json()

    def test_successful_generation_is_validated_persisted_and_traceable(self):
        item = self.uploaded(description="", quiz_source="")
        op_id = self.request(item)
        client = FakeClient(reply(quiz_payload()))
        run_worker(client)

        op = self.operation(op_id)
        self.assertEqual(op["status"], "completed")
        quiz = Quiz.objects.get(pk=op["quiz_id"])
        self.assertEqual(len(quiz.questions), 10)
        self.assertEqual([q["difficulty"] for q in quiz.questions].count("hard"), 4)
        self.assertTrue(all(q["type"] == "mcq" and len(q["options"]) == 4 for q in quiz.questions))

        meta = AIOperation.objects.get(pk=op_id).metadata
        self.assertEqual((meta["prompt_version"], meta["validation"], meta["attempts"]), (PROMPT_VERSION, "passed", 1))
        self.assertEqual((meta["question_count"], meta["difficulty_counts"], meta["language"]),
                         (10, {"easy": 3, "medium": 3, "hard": 4}, "ar-msa"))
        self.assertEqual(meta["source_origin"], "transcript")
        self.assertNotIn("الجملة رقم", json.dumps(meta, ensure_ascii=False))   # no transcript text persisted

    def test_the_prompt_carries_the_complete_transcript_of_the_requested_lesson_only(self):
        mine = self.uploaded(title="درس الخلية", text=lesson_text(2500), description="", quiz_source="")
        other = self.uploaded(title="درس آخر", text="النص المختلف لدرس آخر. " * 100, description="", quiz_source="")
        self.assertNotEqual(mine.id, other.id)
        self.request(mine)
        client = FakeClient(reply(quiz_payload()))
        run_worker(client)

        prompt = client.requests[0].prompt
        self.assertIn("الجملة رقم 1 ", prompt)
        self.assertIn("الجملة رقم 2500 ", prompt)                       # the end of a ~2h lesson, not a prefix
        self.assertNotIn("النص المختلف لدرس آخر", prompt)
        self.assertIn(Transcript.objects.get(item=mine).text, prompt)    # byte-for-byte, nothing sliced
        self.assertIn("درس الخلية", prompt)
        self.assertEqual(len(client.requests), 1)

    def test_missing_or_unusable_transcript_never_reaches_the_model(self):
        client = FakeClient()
        for kwargs in ({"status": None}, {"status": Transcript.Status.PENDING, "text": ""},
                       {"status": Transcript.Status.FAILED, "text": ""}, {"text": "   "}):
            with self.subTest(kwargs=kwargs):
                r = super().request(self.uploaded(description="ملخص", **kwargs))
                self.assertEqual(r.status_code, 409)
        self.assertEqual(AIOperation.objects.count(), 0)
        run_worker(client)
        self.assertEqual(client.requests, [])

    def test_unauthorised_requests_never_reach_the_model(self):
        hidden = self.uploaded(target=False)
        client = FakeClient()
        self.assertEqual(super().request(hidden).status_code, 404)
        run_worker(client)
        self.assertEqual(client.requests, [])
        self.assertEqual(AIOperation.objects.count(), 0)

    def test_invalid_model_output_twice_fails_the_operation_with_no_quiz(self):
        item = self.uploaded()
        op_id = self.request(item)
        bad = quiz_payload()
        bad["questions"] = bad["questions"][:7]
        client = FakeClient(reply(bad), reply(bad))
        run_worker(client)

        op = self.operation(op_id)
        self.assertEqual((op["status"], op["quiz_id"]), ("failed", None))
        self.assertTrue(op["error"])
        self.assertEqual(Quiz.objects.count(), 0)
        self.assertEqual(len(client.requests), 2)                        # bounded: 1 + 1 corrective
        row = AIOperation.objects.get(pk=op_id)
        self.assertEqual(row.metadata["failure_category"], "invalid_output")
        self.assertEqual((row.metadata["validation"], row.metadata["attempts"]), ("failed", 2))
        self.assertEqual(row.result, "")

    def test_a_corrected_second_attempt_completes_normally(self):
        item = self.uploaded()
        op_id = self.request(item)
        bad = quiz_payload()
        bad["questions"][0]["answer_index"] = 7
        client = FakeClient(reply(bad), reply(quiz_payload()))
        run_worker(client)
        self.assertEqual(self.operation(op_id)["status"], "completed")
        self.assertEqual(AIOperation.objects.get(pk=op_id).metadata["attempts"], 2)

    def test_provider_failures_fail_the_operation_without_leaking_detail(self):
        secret = "UPSTREAM-SECRET-DETAIL key=AIzaSyLeakCheck0123456789abcdefgh"
        for exc, category in ((LLMRateLimitError(secret, status=429), "rate_limit"), (LLMTimeoutError(secret), "timeout")):
            with self.subTest(category=category):
                AIOperation.objects.all().delete()
                item = self.uploaded()
                op_id = self.request(item)
                client = FakeClient(exc)
                run_worker(client)
                op = self.operation(op_id)
                self.assertEqual((op["status"], op["quiz_id"]), ("failed", None))
                self.assertNotIn("UPSTREAM", json.dumps(op, ensure_ascii=False))
                self.assertNotIn("AIza", json.dumps(op))
                self.assertEqual(AIOperation.objects.get(pk=op_id).metadata["failure_category"], category)
                self.assertEqual(len(client.requests), 1)

    def test_truncated_output_fails_explicitly(self):
        item = self.uploaded()
        op_id = self.request(item)
        client = FakeClient(reply(quiz_payload(), truncated=True), reply(quiz_payload(), truncated=True))
        run_worker(client)
        self.assertEqual(self.operation(op_id)["status"], "failed")
        self.assertEqual(AIOperation.objects.get(pk=op_id).metadata["failure_category"], "truncated")
        self.assertEqual(Quiz.objects.count(), 0)

    def test_duplicate_processing_calls_the_model_and_creates_the_quiz_once(self):
        item = self.uploaded()
        self.request(item)
        client = FakeClient(reply(quiz_payload()))      # a second call would trip the fake's assertion
        run_worker(client)
        run_worker(client)
        self.assertEqual((len(client.requests), Quiz.objects.count()), (1, 1))

    def test_idempotent_resubmission_does_not_trigger_a_second_generation(self):
        item = self.uploaded()
        first = self.post("quizzes/", {"content_id": item.id, "idempotency_key": "k-1"})
        second = self.post("quizzes/", {"content_id": item.id, "idempotency_key": "k-1"})
        self.assertEqual((first.status_code, second.status_code), (202, 200))
        client = FakeClient(reply(quiz_payload()))
        run_worker(client)
        self.assertEqual((AIOperation.objects.count(), len(client.requests), Quiz.objects.count()), (1, 1, 1))

    def test_missing_language_policy_fails_explicitly_without_calling_the_model(self):
        item = self.uploaded()
        with override_settings(QUIZ_LANGUAGE=""):
            op_id = self.request(item)
            client = FakeClient()
            run_worker(client)
        op = self.operation(op_id)
        self.assertEqual((op["status"], op["quiz_id"]), ("failed", None))
        self.assertTrue(op["error"])
        self.assertEqual(client.requests, [])
        self.assertEqual(AIOperation.objects.get(pk=op_id).metadata["failure_category"], "config")

    def test_operation_metadata_is_never_exposed_to_the_student(self):
        item = self.uploaded()
        op_id = self.request(item)
        run_worker(FakeClient(reply(quiz_payload())))
        op = self.operation(op_id)
        self.assertEqual(set(op), {"id", "status", "error", "quiz_id"})
        detail = self.get(f"quizzes/{op['quiz_id']}/").json()
        self.assertTrue(all(set(q) == {"q", "options"} for q in detail["questions"]))   # no difficulty/answers pre-submit

    def test_scoring_and_review_still_work_on_a_generated_quiz(self):
        item = self.uploaded()
        op_id = self.request(item)
        run_worker(FakeClient(reply(quiz_payload())))
        quiz = Quiz.objects.get(pk=self.operation(op_id)["quiz_id"])
        answers = [q["answer_index"] for q in quiz.questions]
        r = self.post(f"quizzes/{quiz.id}/submit/", {"answers": answers})
        self.assertEqual((r.status_code, r.json()["score"], r.json()["total"]), (200, 10, 10))

    def test_external_video_lessons_use_the_teacher_text_through_the_same_pipeline(self):
        item = self.video(description="الخلية هي الوحدة الأساسية في بناء الكائنات الحية. " * 20, quiz_source="")
        item.target_grades.add(self.grade)
        op_id = self.request(item)
        client = FakeClient(reply(quiz_payload()))
        run_worker(client)
        self.assertEqual(self.operation(op_id)["status"], "completed")
        self.assertEqual(AIOperation.objects.get(pk=op_id).metadata["source_origin"], "teacher_text")

    def test_the_study_assistant_is_unaffected_by_enabling_the_llm_quiz_provider(self):
        from knowledge.models import KBDocument
        doc = KBDocument.objects.create(
            title="الخلية", topic="أحياء", body="الخلية هي الوحدة البنائية والوظيفية الأساسية لجميع الكائنات الحية.")
        doc.publish()
        r = self.post("assistant/", {"prompt": "ما هي الخلية؟"})
        self.assertEqual(r.status_code, 202, r.content)
        client = FakeClient()
        run_worker(client)
        self.assertEqual(self.get(f"assistant/{r.json()['id']}/").json()["status"], "completed")
        self.assertEqual(client.requests, [])          # the model is only used for quizzes
