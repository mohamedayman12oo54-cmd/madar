"""What makes the AI fast, and proof that the speed-ups change no outcome:

* the operation starts the moment it is saved (ai/dispatch.py) — no separate worker needed;
* the content check runs WHILE the first quiz call is in flight (QUIZ_VALIDATION_PARALLEL), yet a rejected lesson
  still never yields a quiz and a rejected lesson never pays for a corrective retry;
* the classifier reads a bounded sample of a very long transcript;
* optional model "thinking" control is only sent when configured.
All with fake clients — no network."""
import threading
import time
from datetime import timedelta
from unittest import mock

from django.core.cache import cache
from django.test import SimpleTestCase, override_settings
from django.utils import timezone

from environments.tenancy_testing import TenantTestCase

from . import dispatch
from .gemini import GeminiClient, thinking_config
from .llm import LLMConfigError, LLMRequest, LLMSettings
from .models import AIOperation
from .processing import process_operation
from .quiz_generation import LLMQuizProvider, QuizGenerationError
from .test_content_validation import validation_reply
from .test_quiz_generation import LESSON, FakeClient, quiz_payload, reply
from .tests import URL, seed_kb


class _Inline:
    """Stands in for the thread pool: runs the job immediately, in the calling thread. (A real pool thread closes
    ITS OWN DB connections when it finishes; here that would close the test's, so it is switched off.)"""

    def __enter__(self):
        self._patch = mock.patch.object(dispatch, "_release_connections")
        self._patch.start()
        return self

    def __exit__(self, *exc):
        self._patch.stop()

    def submit(self, fn, *args):
        fn(*args)


class InProcessDispatchTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        seed_kb()

    def _post(self):
        client = self.client_a
        return client.post(URL, {"prompt": "اشرح نظرية فيثاغورس"}, **self.with_env(self.env_a.id))

    def test_the_default_waits_for_an_external_worker(self):
        with self.captureOnCommitCallbacks(execute=True):
            r = self._post()
        self.assertEqual(r.status_code, 202)
        self.assertEqual(AIOperation.objects.get(pk=r.json()["id"]).status, "pending")

    @override_settings(AI_WORKER_MODE="thread")
    def test_thread_mode_processes_it_right_after_the_request_is_committed(self):
        with _Inline() as inline, mock.patch.object(dispatch, "_pool", return_value=inline):
            with self.captureOnCommitCallbacks(execute=True):
                r = self._post()
        self.assertEqual(r.status_code, 202)
        op = AIOperation.objects.get(pk=r.json()["id"])
        self.assertEqual(op.status, "completed")        # no process_ai_operations was ever run
        self.assertTrue(op.result)

    @override_settings(AI_WORKER_MODE="thread")
    def test_nothing_starts_before_the_transaction_commits(self):
        with _Inline() as inline, mock.patch.object(dispatch, "_pool", return_value=inline) as pool:
            with self.captureOnCommitCallbacks(execute=False) as callbacks:
                r = self._post()
        self.assertEqual(len(callbacks), 1)
        pool.assert_not_called()
        self.assertEqual(AIOperation.objects.get(pk=r.json()["id"]).status, "pending")

    @override_settings(AI_WORKER_MODE="thread")
    def test_a_second_worker_racing_for_the_same_row_does_nothing(self):
        op = AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="اشرح نظرية فيثاغورس")
        with mock.patch("ai.providers.StubTutorProvider.generate", return_value="x") as gen:
            self.assertEqual(process_operation(op.pk), "completed")
            self.assertIsNone(process_operation(op.pk))      # already taken
        self.assertEqual(gen.call_count, 1)

    @override_settings(AI_WORKER_MODE="thread")
    def test_the_sweep_recovers_crashed_and_missed_work(self):
        crashed = AIOperation.objects.create(
            environment=self.env_a, requested_by=self.teacher_a, prompt="اشرح نظرية فيثاغورس",
            status="processing", started_at=timezone.now() - timedelta(minutes=40))
        missed = AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="اشرح نظرية فيثاغورس")
        # (a row that has been processing for 40 minutes was necessarily created at least that long ago)
        AIOperation.objects.filter(pk=missed.pk).update(created_at=timezone.now() - timedelta(minutes=2))
        AIOperation.objects.filter(pk=crashed.pk).update(created_at=timezone.now() - timedelta(minutes=41))
        fresh = AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="اشرح نظرية فيثاغورس")
        with _Inline() as inline, mock.patch.object(dispatch, "_pool", return_value=inline), mock.patch.object(dispatch, "_last_sweep", 0.0):
            dispatch._sweep()
        for op in (crashed, missed, fresh):
            op.refresh_from_db()
        self.assertEqual(crashed.status, "completed")
        self.assertEqual(missed.status, "completed")
        self.assertEqual(fresh.status, "pending")           # still inside its own dispatch grace period

    @override_settings(AI_WORKER_MODE="bogus")
    def test_unknown_mode_is_not_thread_mode(self):
        self.assertFalse(dispatch.enabled())


class RealThreadDispatchTests(SimpleTestCase):
    """The same thing with a REAL thread, a real second DB connection and real commits.

    Deliberately NOT a TransactionTestCase: that would empty every table afterwards — including the plans the
    migrations seed, which billing's own TransactionTestCase needs — so the rows are created for real and removed
    again by hand."""

    databases = {"default"}

    def setUp(self):
        from accounts.models import User
        from environments.models import Environment, EnvironmentMembership
        from environments.tenancy_testing import PASSWORD
        from knowledge.models import KBDocument
        from rest_framework.test import APIClient

        cache.clear()
        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="t", email="thread-dispatch@example.com", phone="201020000078",
            password=PASSWORD, is_active=True)
        self.env = Environment.objects.create(owner=self.teacher, name="بيئة")
        EnvironmentMembership.objects.create(user=self.teacher, environment=self.env, role="owner")
        self.doc = seed_kb()
        self.addCleanup(self._remove_rows)
        self.client = APIClient()
        token = self.client.post("/api/v1/auth/teacher/login/", {"identifier": "thread-dispatch@example.com", "password": PASSWORD}).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + token)
        self.addCleanup(self._stop_pool)     # runs first (LIFO): the pool is idle before its rows go

    def _remove_rows(self):
        from accounts.models import User
        from environments.models import Environment
        AIOperation.objects.filter(environment=self.env).delete()
        self.doc.delete()
        Environment.objects.filter(pk=self.env.pk).delete()
        User.objects.filter(pk=self.teacher.pk).delete()

    @staticmethod
    def _stop_pool():
        with dispatch._lock:
            pool, dispatch._executor = dispatch._executor, None
        if pool:
            pool.shutdown(wait=True)

    @override_settings(AI_WORKER_MODE="thread")
    def test_the_answer_arrives_with_no_worker_running_and_without_waiting_for_a_poll_interval(self):
        t0 = time.monotonic()
        r = self.client.post(URL, {"prompt": "اشرح نظرية فيثاغورس"}, HTTP_X_MADAR_ENVIRONMENT=str(self.env.id))
        self.assertEqual(r.status_code, 202, r.content)
        status = None
        while time.monotonic() - t0 < 10:
            op = self.client.get(f"{URL}{r.json()['id']}/", HTTP_X_MADAR_ENVIRONMENT=str(self.env.id)).json()
            status = op["status"]
            if status in ("completed", "failed"):
                break
            time.sleep(0.02)
        self.assertEqual(status, "completed", op)
        self.assertLess(time.monotonic() - t0, 3.0)      # a polling worker would add up to its whole interval
        self.assertTrue(op["result"])
        self.assertEqual(op["sources"][0]["title"], "نظرية فيثاغورس")


# ------------------------------------------------------------------ parallel check --
class _Routing:
    """A fake model that tells the two prompts apart and records the order/overlap of the calls."""

    def __init__(self, *, check, generate, gate=None):
        self.check, self.generate = check, list(generate)
        self.requests = []
        self.gate = gate or {}
        self.gen_started = threading.Event()
        self.check_started = threading.Event()
        self.check_done = threading.Event()
        self._lock = threading.Lock()

    def complete(self, request):
        with self._lock:
            self.requests.append(request)
        if "content classifier" in request.system:
            self.check_started.set()
            if self.gate.get("check_waits_for_generation"):
                assert self.gen_started.wait(5), "the check was not run alongside generation"
            self.check_done.set()
            return self.check
        self.gen_started.set()
        if self.gate.get("generation_waits_for_check"):
            assert self.check_done.wait(5), "the check never finished"
        elif self.gate.get("generation_waits_for_check_start"):
            assert self.check_started.wait(5), "the check was not started alongside generation"
        outcome = self.generate.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    @property
    def generation_calls(self):
        return [r for r in self.requests if "content classifier" not in r.system]


def provider(client, **kw):
    from .quiz_contract import QuizGenerationConfig
    return LLMQuizProvider(client=client, config=QuizGenerationConfig(language="ar-msa"),
                           validate_content=True, parallel_validation=True, **kw)


EVIDENCE = {"title": "الخلية", "text": LESSON, "source": {"origin": "transcript"}}


class ParallelContentCheckTests(SimpleTestCase):
    def test_the_check_and_the_first_generation_run_at_the_same_time(self):
        client = _Routing(check=validation_reply(), generate=[reply(quiz_payload())],
                          gate={"check_waits_for_generation": True, "generation_waits_for_check_start": True})
        result = provider(client).generate_quiz_result(EVIDENCE)
        self.assertEqual(len(result.questions), 10)
        self.assertTrue(result.metadata["content_validation"]["is_educational"])
        self.assertEqual(result.metadata["validation"], "passed")
        self.assertEqual(set(result.metadata["timings_ms"]), {"content_check", "generation", "total"})

    def test_a_rejected_lesson_never_yields_a_quiz_even_though_one_was_generated(self):
        client = _Routing(check=validation_reply(is_educational=False, category="vlog"), generate=[reply(quiz_payload())])
        with self.assertRaises(QuizGenerationError) as ctx:
            provider(client).generate_quiz_result(EVIDENCE)
        self.assertEqual(ctx.exception.category, "non_educational")
        self.assertIn("لا يحتوي هذا الفيديو على محتوى تعليمي", str(ctx.exception))
        self.assertEqual(ctx.exception.metadata["content_category"], "vlog")

    def test_a_rejected_lesson_does_not_pay_for_a_corrective_retry(self):
        bad = reply({"questions": []})
        client = _Routing(check=validation_reply(is_educational=False), generate=[bad, bad],
                          gate={"generation_waits_for_check": True})
        with self.assertRaises(QuizGenerationError) as ctx:
            provider(client, max_attempts=2).generate_quiz_result(EVIDENCE)
        self.assertEqual(ctx.exception.category, "non_educational")
        self.assertEqual(len(client.generation_calls), 1)

    def test_the_verdict_wins_over_a_generation_failure_when_it_is_already_known(self):
        from .llm import LLMProviderError
        client = _Routing(check=validation_reply(is_educational=False),
                          generate=[LLMProviderError("boom", status=500)], gate={"generation_waits_for_check": True})
        with self.assertRaises(QuizGenerationError) as ctx:
            provider(client).generate_quiz_result(EVIDENCE)
        self.assertEqual(ctx.exception.category, "non_educational")

    def test_an_unusable_check_answer_means_no_quiz(self):
        client = _Routing(check=reply("not json"), generate=[reply(quiz_payload())])
        with self.assertRaises(QuizGenerationError) as ctx:
            provider(client).generate_quiz_result(EVIDENCE)
        self.assertEqual(ctx.exception.category, "content_validation_failed")

    def test_a_generation_failure_is_reported_as_itself_when_the_lesson_is_fine(self):
        from .llm import LLMRateLimitError
        client = _Routing(check=validation_reply(), generate=[LLMRateLimitError("slow down", status=429)])
        with self.assertRaises(QuizGenerationError) as ctx:
            provider(client).generate_quiz_result(EVIDENCE)
        self.assertEqual(ctx.exception.category, "rate_limit")
        self.assertIn("timings_ms", ctx.exception.metadata)

    def test_sequential_mode_still_checks_first_and_never_generates_for_a_rejected_lesson(self):
        client = FakeClient(validation_reply(is_educational=False))
        seq = LLMQuizProvider(client=client, validate_content=True, parallel_validation=False,
                              config=__import__("ai.quiz_contract", fromlist=["x"]).QuizGenerationConfig(language="ar-msa"))
        with self.assertRaises(QuizGenerationError):
            seq.generate_quiz_result(EVIDENCE)
        self.assertEqual(len(client.requests), 1)


class ClassifierSampleTests(SimpleTestCase):
    def long_text(self, n=40000):
        return ("البداية " + "س" * 100) + ("م" * n) + ("النهاية " + "ص" * 100)

    def test_a_long_transcript_is_sampled_for_the_check_but_generation_gets_all_of_it(self):
        text = self.long_text()
        client = FakeClient(validation_reply(), reply(quiz_payload()))
        p = LLMQuizProvider(client=client, validate_content=True, parallel_validation=False, validation_sample_chars=9000,
                            config=__import__("ai.quiz_contract", fromlist=["x"]).QuizGenerationConfig(language="ar-msa"))
        result = p.generate_quiz_result({"title": "t", "text": text, "source": {"origin": "transcript"}})
        check_req, gen_req = client.requests
        self.assertLess(len(check_req.prompt), 12000)
        self.assertIn("البداية", check_req.prompt)
        self.assertIn("النهاية", check_req.prompt)
        self.assertIn("[…]", check_req.prompt)
        self.assertGreater(len(gen_req.prompt), len(text))      # the quiz is still built from everything
        self.assertEqual(result.metadata["validation_sample_chars"], len(p._classifier_sample(text)))

    def test_a_short_transcript_and_a_zero_limit_are_sent_whole(self):
        p = LLMQuizProvider(validation_sample_chars=9000)
        self.assertEqual(p._classifier_sample("قصير"), "قصير")
        self.assertEqual(LLMQuizProvider(validation_sample_chars=0)._classifier_sample("x" * 50000), "x" * 50000)


# --------------------------------------------------------------------- thinking --
class ThinkingControlTests(SimpleTestCase):
    def test_parsing(self):
        self.assertIsNone(thinking_config(""))
        self.assertIsNone(thinking_config(None))
        self.assertEqual(thinking_config("0"), {"thinkingBudget": 0})
        self.assertEqual(thinking_config(" 2048 "), {"thinkingBudget": 2048})
        self.assertEqual(thinking_config("-1"), {"thinkingBudget": -1})
        self.assertEqual(thinking_config("LOW"), {"thinkingLevel": "low"})
        self.assertEqual(thinking_config("minimal"), {"thinkingLevel": "minimal"})
        for bad in ("fast", "-5", "1.5", "low medium"):
            with self.subTest(bad=bad), self.assertRaises(LLMConfigError):
                thinking_config(bad)

    def body(self, **kw):
        c = GeminiClient(api_key="k" * 20, model="m", llm_settings=LLMSettings(), **kw)
        return c._build_body(LLMRequest(prompt="hi", json_output=True))

    def test_nothing_is_sent_unless_configured(self):
        self.assertNotIn("thinkingConfig", self.body().get("generationConfig", {}))

    def test_a_configured_value_is_sent(self):
        self.assertEqual(self.body(thinking="0")["generationConfig"]["thinkingConfig"], {"thinkingBudget": 0})
        self.assertEqual(self.body(thinking="low")["generationConfig"]["thinkingConfig"], {"thinkingLevel": "low"})

    def test_an_invalid_value_fails_before_any_request(self):
        with self.assertRaises(LLMConfigError):
            GeminiClient(api_key="k" * 20, model="m", thinking="fast")


class StateSuggestionWordingTests(SimpleTestCase):
    def test_same_decision_as_the_stub_without_the_test_mode_label(self):
        from .providers import StubTutorProvider
        ev = {"present": 5, "absent": 5, "studied": 4, "not_studied": 4}
        stub_state, stub_text = StubTutorProvider().recommend_state(ev)
        state, text = LLMQuizProvider().recommend_state(ev)
        self.assertEqual(state, stub_state)
        self.assertIn("وضع تجريبي", stub_text)
        self.assertNotIn("وضع تجريبي", text)
        self.assertIn("5 من 10", text)
