"""Phase 5 — AI operations: asynchronous submit/poll/result, selective
idempotency, tenant isolation, and worker safety."""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.throttling import SimpleRateThrottle

from environments.tenancy_testing import TenantTestCase

from .models import AIOperation
from .providers import AIProvider, AIProviderError, StubTutorProvider

URL = "/api/v1/ai/operations/"


def op_url(pk):
    return f"{URL}{pk}/"


def run_worker(*args):
    out = StringIO()
    call_command("process_ai_operations", *args, stdout=out)
    return out.getvalue()


class SubmitAndPollTests(TenantTestCase):
    def submit(self, client=None, env=None, **body):
        client = client or self.client_a
        env = env or self.env_a
        return client.post(URL, body, **self.with_env(env.id))

    def test_submit_returns_202_with_an_id_and_pending_status_and_does_no_work(self):
        with mock.patch("ai.providers.StubTutorProvider.generate") as gen:
            r = self.submit(prompt="اشرح نظرية فيثاغورس")
        self.assertEqual(r.status_code, 202, r.content)
        self.assertEqual(r.json()["status"], "pending")
        self.assertEqual(r.json()["result"], "")
        gen.assert_not_called()  # the request cycle never touches the model

    def test_full_lifecycle_submit_poll_process_poll(self):
        op_id = self.submit(prompt="ما هو الجذر التربيعي؟").json()["id"]
        self.assertEqual(self.client_a.get(op_url(op_id), **self.with_env(self.env_a.id)).json()["status"], "pending")

        out = run_worker()
        self.assertIn("1 completed, 0 failed", out)

        done = self.client_a.get(op_url(op_id), **self.with_env(self.env_a.id)).json()
        self.assertEqual(done["status"], "completed")
        self.assertIn("وضع تجريبي", done["result"])  # the stub labels itself in-band
        self.assertIsNotNone(done["completed_at"])

    def test_result_is_persisted_in_madar_not_refetched_from_the_provider_on_poll(self):
        op_id = self.submit(prompt="سؤال").json()["id"]
        run_worker()
        with mock.patch("ai.providers.StubTutorProvider.generate") as gen:
            self.client_a.get(op_url(op_id), **self.with_env(self.env_a.id))
            self.client_a.get(op_url(op_id), **self.with_env(self.env_a.id))
        gen.assert_not_called()

    def test_provider_failure_marks_failed_explicitly_with_no_result(self):
        op_id = self.submit(prompt="سؤال").json()["id"]

        class Boom(AIProvider):
            def generate(self, prompt):
                raise AIProviderError("upstream unavailable")

        with mock.patch("ai.management.commands.process_ai_operations.get_provider", return_value=Boom()):
            out = run_worker()
        self.assertIn("0 completed, 1 failed", out)
        failed = self.client_a.get(op_url(op_id), **self.with_env(self.env_a.id)).json()
        self.assertEqual(failed["status"], "failed")
        self.assertEqual(failed["error"], "upstream unavailable")
        self.assertEqual(failed["result"], "")

    def test_unexpected_provider_exception_is_failed_without_leaking_internals(self):
        op_id = self.submit(prompt="سؤال").json()["id"]

        class Weird(AIProvider):
            def generate(self, prompt):
                raise RuntimeError("secret /srv/path api_key=sk-123")

        with mock.patch("ai.management.commands.process_ai_operations.get_provider", return_value=Weird()):
            run_worker()
        failed = self.client_a.get(op_url(op_id), **self.with_env(self.env_a.id)).json()
        self.assertEqual(failed["status"], "failed")
        self.assertNotIn("sk-123", str(failed))
        self.assertNotIn("/srv/path", str(failed))

    def test_failed_operation_can_be_retried_by_submitting_again(self):
        first = self.submit(prompt="سؤال").json()["id"]
        AIOperation.objects.filter(pk=first).update(status="failed", error="x")
        second = self.submit(prompt="سؤال").json()["id"]
        self.assertNotEqual(first, second)

    def test_prompt_validation(self):
        self.assertEqual(self.submit(prompt="   ").status_code, 400)
        self.assertEqual(self.submit().status_code, 400)
        self.assertEqual(self.submit(prompt="x" * 2001).status_code, 400)
        self.assertEqual(self.submit(prompt="x" * 2000).status_code, 202)

    def test_requires_environment_header_and_auth(self):
        self.assertEqual(self.client_a.post(URL, {"prompt": "x"}).status_code, 400)
        from rest_framework.test import APIClient
        self.assertEqual(APIClient().post(URL, {"prompt": "x"}, **self.with_env(self.env_a.id)).status_code, 401)


class SelectiveIdempotencyTests(TenantTestCase):
    def submit(self, prompt="سؤال", key=None, client=None, env=None):
        body = {"prompt": prompt}
        if key is not None:
            body["idempotency_key"] = key
        return (client or self.client_a).post(URL, body, **self.with_env((env or self.env_a).id))

    def test_same_key_and_prompt_returns_the_same_operation_not_a_duplicate(self):
        first = self.submit(key="abc")
        second = self.submit(key="abc")
        self.assertEqual(first.status_code, 202)
        self.assertEqual(second.status_code, 200)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(AIOperation.objects.count(), 1)

    def test_same_key_with_a_different_prompt_is_a_409_conflict(self):
        self.submit(prompt="أ", key="abc")
        r = self.submit(prompt="ب", key="abc")
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["code"], "idempotency_conflict")
        self.assertEqual(AIOperation.objects.count(), 1)

    def test_no_key_means_no_deduplication_it_is_selective_not_universal(self):
        self.submit(); self.submit(); self.submit(key="")
        self.assertEqual(AIOperation.objects.count(), 3)

    def test_replay_of_a_completed_operation_returns_its_result(self):
        first = self.submit(key="k1").json()["id"]
        run_worker()
        again = self.submit(key="k1")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["id"], first)
        self.assertEqual(again.json()["status"], "completed")

    def test_keys_are_scoped_per_user_and_environment(self):
        self.submit(key="same")
        other = self.submit(key="same", client=self.client_b, env=self.env_b)
        self.assertEqual(other.status_code, 202)
        self.assertEqual(AIOperation.objects.count(), 2)

    def test_db_constraint_backs_the_api_check(self):
        AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="x", idempotency_key="dup")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="y", idempotency_key="dup")

    def test_null_keys_never_collide_at_the_db_level(self):
        for _ in range(3):
            AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="x")
        self.assertEqual(AIOperation.objects.count(), 3)


class TenancyAndIsolationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.op = AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="سري")

    def test_cannot_poll_another_teachers_operation(self):
        self.assert_cross_tenant_denied("get", op_url(self.op.id))

    def test_own_header_but_someone_elses_id_is_404(self):
        r = self.client_b.get(op_url(self.op.id), **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)

    def test_list_shows_only_my_operations(self):
        AIOperation.objects.create(environment=self.env_b, requested_by=self.teacher_b, prompt="لآخر")
        r = self.client_a.get(URL, **self.with_env(self.env_a.id))
        self.assertEqual([o["id"] for o in r.json()["results"]], [self.op.id])

    def test_cross_tenant_list_and_submit_denied(self):
        self.assert_cross_tenant_denied("get", URL)
        self.assert_cross_tenant_denied("post", URL, body={"prompt": "x"})
        self.assertEqual(AIOperation.objects.filter(environment=self.env_a).count(), 1)

    def test_response_never_exposes_owner_or_environment_ids(self):
        keys = set(self.client_a.get(op_url(self.op.id), **self.with_env(self.env_a.id)).json())
        self.assertFalse(keys & {"requested_by", "environment", "user", "idempotency_key"})

    def test_general_tutor_by_construction_no_link_to_student_records(self):
        """Spec: the assistant is NOT a personalized student-record retrieval
        system. Structurally: AIOperation has no relation to any student-,
        enrollment-, payment-, note- or session-owned model."""
        related = {f.related_model.__name__ for f in AIOperation._meta.get_fields() if f.is_relation and f.related_model}
        self.assertEqual(related, {"Environment", "User"})


class SubmitThrottleTests(TenantTestCase):
    def test_submissions_are_rate_limited_per_teacher_but_listing_is_not(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"ai-submit": "2/hour"}):
            codes = [self.client_a.post(URL, {"prompt": f"q{i}"}, **self.with_env(self.env_a.id)).status_code for i in range(3)]
            listing = [self.client_a.get(URL, **self.with_env(self.env_a.id)).status_code for _ in range(5)]
            other_teacher = self.client_b.post(URL, {"prompt": "q"}, **self.with_env(self.env_b.id)).status_code
        self.assertEqual(codes, [202, 202, 429])
        self.assertEqual(set(listing), {200})
        self.assertEqual(other_teacher, 202)


class WorkerSafetyTests(TenantTestCase):
    def make(self, **kw):
        return AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="q", **kw)

    def test_worker_only_processes_pending(self):
        done = self.make(status="completed", result="keep")
        run_worker()
        done.refresh_from_db()
        self.assertEqual(done.result, "keep")

    def test_claim_is_atomic_only_one_caller_wins(self):
        from ai.management.commands.process_ai_operations import claim
        op = self.make()
        self.assertTrue(claim(op.pk))    # first worker wins
        self.assertFalse(claim(op.pk))   # a second worker racing for it loses
        op.refresh_from_db()
        self.assertEqual(op.status, "processing")

    def test_a_lost_claim_means_the_provider_is_never_called(self):
        """Worker A lists the row as pending, but worker B claims it before A
        does — A must skip it (the provider is called at most once)."""
        op = self.make()
        with mock.patch("ai.management.commands.process_ai_operations.claim", return_value=False), \
             mock.patch("ai.providers.StubTutorProvider.generate") as gen:
            out = run_worker()
        gen.assert_not_called()
        self.assertIn("0 completed, 0 failed", out)
        op.refresh_from_db()
        self.assertEqual(op.status, "pending")

    def test_stale_processing_rows_are_requeued_and_then_completed(self):
        op = self.make(status="processing", started_at=timezone.now() - timedelta(minutes=45))
        out = run_worker("--requeue-stale-minutes", "15")
        op.refresh_from_db()
        self.assertEqual(op.status, "completed")
        self.assertIn("requeued 1 stale", out)

    def test_fresh_processing_rows_are_left_alone(self):
        op = self.make(status="processing", started_at=timezone.now() - timedelta(minutes=1))
        run_worker("--requeue-stale-minutes", "15")
        op.refresh_from_db()
        self.assertEqual(op.status, "processing")

    def test_limit_is_respected_and_oldest_first(self):
        first = self.make(); second = self.make()
        run_worker("--limit", "1")
        first.refresh_from_db(); second.refresh_from_db()
        self.assertEqual((first.status, second.status), ("completed", "pending"))


class LoopModeTests(TenantTestCase):
    def test_loop_picks_up_work_that_arrives_between_iterations(self):
        seen = []

        def fake_sleep(_):
            # "new work arrives" while the worker is sleeping
            AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="late")
            seen.append(1)

        AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="early")
        with mock.patch("ai.management.commands.process_ai_operations.time.sleep", side_effect=fake_sleep):
            out = StringIO()
            call_command("process_ai_operations", "--loop", "--interval", "0", "--max-iterations", "2", stdout=out)
        self.assertEqual(AIOperation.objects.filter(status="completed").count(), 2)
        self.assertEqual(len(seen), 1)

    def test_without_loop_it_runs_exactly_once_and_never_sleeps(self):
        with mock.patch("ai.management.commands.process_ai_operations.time.sleep") as sleep:
            run_worker()
        sleep.assert_not_called()


class ProviderTests(TenantTestCase):
    def test_stub_is_clearly_labelled_and_deterministic(self):
        a = StubTutorProvider().generate("سؤال")
        self.assertIn("وضع تجريبي", a)
        self.assertEqual(a, StubTutorProvider().generate("سؤال"))

    def test_unknown_provider_setting_fails_loudly(self):
        from django.test import override_settings
        from .providers import get_provider
        with override_settings(AI_PROVIDER="nope"):
            with self.assertRaises(AIProviderError):
                get_provider()

    def test_base_provider_is_an_interface(self):
        with self.assertRaises(NotImplementedError):
            AIProvider().generate("x")
