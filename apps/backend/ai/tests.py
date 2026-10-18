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


def seed_kb(*, published=True, title="نظرية فيثاغورس", topic="رياضيات",
            body=("نظرية فيثاغورس تنص على أن مربع الوتر في المثلث القائم يساوي "
                  "مجموع مربعي الضلعين الآخرين. الجذر التربيعي لعدد هو العدد الذي "
                  "إذا ضرب في نفسه أعطى ذلك العدد. سؤال شائع في الرياضيات.")):
    """The Study Assistant is grounded in the PUBLISHED Knowledge Base, so any
    test that expects an answer must first curate something for it to use."""
    from knowledge.models import KBDocument

    doc = KBDocument.objects.create(title=title, topic=topic, body=body)
    if published:
        doc.publish()
    return doc


def run_worker(*args):
    out = StringIO()
    call_command("process_ai_operations", *args, stdout=out)
    return out.getvalue()


class SubmitAndPollTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        seed_kb()

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
            def generate(self, prompt, context=""):
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
    def setUp(self):
        super().setUp()
        seed_kb()

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

    def test_general_tutor_by_construction_cannot_reference_a_student(self):
        """Spec (PD-1): the assistant is NOT a student-record retrieval system.
        Only the bounded `state_recommendation` kind may carry an enrollment;
        the database itself refuses an assistant operation that does."""
        from django.db import IntegrityError, transaction

        from academics.models import Grade
        from accounts.testing import make_enrollment

        student = self.make_student_in(self.env_a, "201066600001")
        enrollment = make_enrollment(self.env_a, student, Grade.objects.create(environment=self.env_a, name="ع"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            AIOperation.objects.create(
                environment=self.env_a, requested_by=self.teacher_a, prompt="x",
                kind=AIOperation.Kind.ASSISTANT, enrollment=enrollment,
            )


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
    def setUp(self):
        super().setUp()
        seed_kb()

    def make(self, **kw):
        return AIOperation.objects.create(
            environment=self.env_a, requested_by=self.teacher_a, prompt="اشرح نظرية فيثاغورس", **kw)

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


class WorkerEntitlementRecheckTests(TenantTestCase):
    """BILL-WU-011 AC-6: the submit-time entitlement check does not
    guarantee the Environment is still entitled by the time the worker
    actually picks a gated operation up. An operation submitted while
    entitled, whose Environment loses the capability before this worker
    claims it, ends `failed` with a stable error and creates no Quiz row
    (ADR-006 "no partial result")."""

    def setUp(self):
        super().setUp()
        from academics.models import Grade, Group
        from accounts.testing import make_enrollment
        from billing.models import AmountOwed, BillingPeriod, PaymentAttempt, Plan, Subscription
        from content.models import ContentItem

        self.Subscription = Subscription
        self.grade = Grade.objects.create(environment=self.env_a, name="g")
        group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        student = self.make_student_in(self.env_a, "201066622222")
        self.enrollment = make_enrollment(self.env_a, student, self.grade, group)
        self.item = ContentItem.objects.create(
            environment=self.env_a, title="t", description="d" * 60, published_at=timezone.now(),
        )

        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        now = timezone.now()
        self.subscription = Subscription.objects.create(
            environment=self.env_a, plan=plan, state=Subscription.State.ACTIVE,
            current_period_start=now - timedelta(days=1), current_period_end=now + timedelta(days=29),
        )
        period = BillingPeriod.objects.create(
            environment=self.env_a, subscription=self.subscription,
            period_start=self.subscription.current_period_start, period_end=self.subscription.current_period_end,
        )
        AmountOwed.objects.create(
            environment=self.env_a, billing_period=period, amount_minor_units=plan.price_minor_units,
            currency=plan.currency, status=AmountOwed.Status.SATISFIED,
        )
        PaymentAttempt.objects.create(
            environment=self.env_a, subscription=self.subscription, billing_period=period,
            merchant_order_id="wu011-worker-recheck", amount_minor_units=plan.price_minor_units,
            currency=plan.currency, status=PaymentAttempt.Status.SUCCEEDED,
        )

    def test_a_capability_lost_between_submit_and_processing_ends_failed_with_no_quiz(self):
        op = AIOperation.objects.create(
            environment=self.env_a, requested_by=self.teacher_a, kind=AIOperation.Kind.QUIZ_GENERATION,
            enrollment=self.enrollment, content=self.item, prompt="quiz content",
            evidence={"title": "t", "text": "x" * 60},
        )

        # The plan is removed/downgraded between submit and the worker run.
        self.subscription.plan = None
        self.subscription.state = self.Subscription.State.EXPIRED
        self.subscription.save(update_fields=["plan", "state"])

        run_worker()

        op.refresh_from_db()
        self.assertEqual(op.status, AIOperation.Status.FAILED)
        from studentarea.models import Quiz

        self.assertFalse(Quiz.objects.filter(operation=op).exists())


class LoopModeTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        seed_kb()

    def test_loop_picks_up_work_that_arrives_between_iterations(self):
        seen = []

        def fake_sleep(_):
            # "new work arrives" while the worker is sleeping
            AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="اشرح نظرية فيثاغورس مرة أخرى")
            seen.append(1)

        AIOperation.objects.create(environment=self.env_a, requested_by=self.teacher_a, prompt="اشرح نظرية فيثاغورس")
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
        ctx = "[درس] مادة منشورة من قاعدة المعرفة."
        a = StubTutorProvider().generate("سؤال", ctx)
        self.assertIn("وضع تجريبي", a)
        self.assertEqual(a, StubTutorProvider().generate("سؤال", ctx))

    def test_stub_refuses_to_answer_without_knowledge_base_grounding(self):
        """No curated source => no answer. The tutor must never answer from
        memory (docs: bounded source contract)."""
        with self.assertRaises(AIProviderError):
            StubTutorProvider().generate("سؤال", "")

    def test_unknown_provider_setting_fails_loudly(self):
        from django.test import override_settings
        from .providers import get_provider
        with override_settings(AI_PROVIDER="nope"):
            with self.assertRaises(AIProviderError):
                get_provider()

    def test_base_provider_is_an_interface(self):
        with self.assertRaises(NotImplementedError):
            AIProvider().generate("x")
