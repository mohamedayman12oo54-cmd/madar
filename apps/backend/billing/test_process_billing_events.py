"""
BILL-WU-022 — recovery worker claim and recovery tests.
"""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import User
from environments.models import Environment, EnvironmentMembership
from environments.tenancy_testing import TenantTestCase

from billing import events
from billing.management.commands.process_billing_events import PROCESSING, claim
from billing.models import PaymentAttempt, Plan, ProviderEvent, Subscription


def run_worker(*args):
    out = StringIO()
    call_command("process_billing_events", *args, stdout=out)
    return out.getvalue()


def _make_attempt(environment, subscription, plan, merchant_order_id):
    return PaymentAttempt.objects.create(
        environment=environment, subscription=subscription, billing_period=None,
        merchant_order_id=merchant_order_id, amount_minor_units=plan.price_minor_units,
        currency=plan.currency, status=PaymentAttempt.Status.PENDING,
    )


def _make_event(dedup_key, merchant_order_id, provider_transaction_id, amount, currency,
                 processing_status=ProviderEvent.ProcessingStatus.RECEIVED, attempts_count=0):
    return ProviderEvent.objects.create(
        dedup_key=dedup_key, mode="test", event_type="charge", transaction_status="SUCCESS",
        provider_transaction_id=provider_transaction_id, provider_order_id=f"{provider_transaction_id}-ord",
        signature_valid=True, processing_status=processing_status, attempts_count=attempts_count,
        redacted_payload={"merchant_order_id": merchant_order_id, "amount_minor_units": amount, "currency": currency},
    )


class WorkerAppliesReceivedEventsTests(TenantTestCase):
    """AC-BILL-022-1."""

    def test_a_received_event_is_applied_by_one_run(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.TRIAL)
        attempt = _make_attempt(self.env_a, subscription, plan, "wrk-1")
        event = _make_event("dk-wrk-1", "wrk-1", "txn-wrk-1", plan.price_minor_units, plan.currency)

        out = run_worker()

        attempt.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.PROCESSED)
        self.assertIn("1 resolved", out)

    def test_an_already_terminal_event_is_left_alone(self):
        event = ProviderEvent.objects.create(
            dedup_key="dk-done", mode="test", event_type="charge", transaction_status="SUCCESS",
            provider_transaction_id="txn-done", provider_order_id="ord-done", signature_valid=True,
            processing_status=ProviderEvent.ProcessingStatus.PROCESSED,
            redacted_payload={"merchant_order_id": "no-such-attempt"},
        )
        run_worker()
        event.refresh_from_db()
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.PROCESSED)


class ClaimAtomicityTests(TransactionTestCase):
    """AC-BILL-022-2. Needs a real (non test-wrapped) transaction boundary
    — `TenantTestCase`'s base wraps every test in one outer atomic block.
    Uses a minimal direct fixture, like the other `TransactionTestCase`
    classes in this module (same pattern as `ai.tests.WorkerSafetyTests
    .test_claim_is_atomic_only_one_caller_wins`, this codebase's existing
    precedent for testing an atomic claim step)."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="t", email="t-022-claim@example.com", phone="201020000088",
            password="Str0ng!Pass", is_active=True,
        )
        self.env = Environment.objects.create(owner=self.teacher, name="env")
        EnvironmentMembership.objects.create(user=self.teacher, environment=self.env, role=EnvironmentMembership.Role.OWNER)
        self.plan, _ = Plan.objects.get_or_create(
            key=Plan.Key.PLAN_1,
            defaults={"name": "Plan 1", "price_minor_units": 100000, "currency": "EGP", "max_students": 400},
        )
        self.subscription = Subscription.objects.create(environment=self.env, plan=self.plan, state=Subscription.State.TRIAL)

    def test_claim_is_atomic_only_one_caller_wins(self):
        event = _make_event("dk-claim-atomic", "wrk-claim-atomic", "txn-claim-atomic", self.plan.price_minor_units, self.plan.currency)

        self.assertTrue(claim(event.pk))   # first worker wins
        self.assertFalse(claim(event.pk))  # a second worker racing for it loses

        event.refresh_from_db()
        self.assertEqual(event.processing_status, PROCESSING)

    def test_two_runs_apply_the_event_exactly_once(self):
        attempt = _make_attempt(self.env, self.subscription, self.plan, "wrk-claim-e2e")
        _make_event("dk-claim-e2e", "wrk-claim-e2e", "txn-claim-e2e", self.plan.price_minor_units, self.plan.currency)

        run_worker()
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)

        # A second run (simulating a second worker arriving after the
        # first already resolved it) finds nothing RECEIVED to claim —
        # `events.apply` is never even reached a second time.
        with mock.patch("billing.management.commands.process_billing_events.events.apply") as apply_mock:
            run_worker()
        apply_mock.assert_not_called()


class StaleRequeueTests(TenantTestCase):
    """AC-BILL-022-3."""

    def test_a_stale_processing_event_is_requeued_and_applied(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.TRIAL)
        attempt = _make_attempt(self.env_a, subscription, plan, "wrk-stale")
        event = _make_event(
            "dk-stale", "wrk-stale", "txn-stale", plan.price_minor_units, plan.currency,
            processing_status=PROCESSING,
        )
        # `received_at` is auto_now_add (set at creation); force it old
        # enough to look stale — a plain QuerySet `.update()` bypasses
        # auto_now_add, which only applies inside `Model.save()`.
        ProviderEvent.objects.filter(pk=event.pk).update(received_at=timezone.now() - timedelta(minutes=45))

        out = run_worker("--requeue-stale-minutes", "15")

        attempt.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.PROCESSED)
        self.assertIn("requeued 1 stale", out)

    def test_a_fresh_processing_event_is_left_alone(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.TRIAL)
        attempt = _make_attempt(self.env_a, subscription, plan, "wrk-fresh")
        event = _make_event(
            "dk-fresh", "wrk-fresh", "txn-fresh", plan.price_minor_units, plan.currency,
            processing_status=PROCESSING,
        )

        run_worker("--requeue-stale-minutes", "15")

        attempt.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.PENDING)
        self.assertEqual(event.processing_status, PROCESSING)


class PoisonEventTests(TenantTestCase):
    """AC-BILL-022-4."""

    def test_a_consistently_failing_event_ends_needs_attention_without_blocking_others(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.TRIAL)

        poison_attempt = _make_attempt(self.env_a, subscription, plan, "wrk-poison")
        poison_event = _make_event("dk-poison", "wrk-poison", "txn-poison", plan.price_minor_units, plan.currency)

        # A second LIVE checkout on the same subscription is now structurally impossible
        # (unique_non_terminal_checkout_per_subscription), so the "good" event belongs to
        # another environment's subscription.
        subscription_b = Subscription.objects.create(environment=self.env_b, plan=plan, state=Subscription.State.TRIAL)
        good_attempt = _make_attempt(self.env_b, subscription_b, plan, "wrk-good")
        good_event = _make_event("dk-good", "wrk-good", "txn-good", plan.price_minor_units, plan.currency)

        real_apply = events.apply  # captured before patching: `mock.patch`
        # replaces `apply` on the shared `billing.events` module object, so
        # calling `events.apply` from inside the side_effect itself would
        # recurse into the mock, not the original function.

        def flaky_apply(event):
            if event.pk == poison_event.pk:
                raise RuntimeError("simulated persistent failure")
            return real_apply(event)

        with mock.patch("billing.management.commands.process_billing_events.events.apply", side_effect=flaky_apply):
            for _ in range(5):
                run_worker("--max-attempts", "3")

        poison_event.refresh_from_db()
        good_event.refresh_from_db()
        poison_attempt.refresh_from_db()
        good_attempt.refresh_from_db()

        self.assertEqual(poison_event.processing_status, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY)
        self.assertIn("needs_attention", poison_event.last_error)
        self.assertEqual(poison_event.attempts_count, 3)
        self.assertEqual(poison_attempt.status, PaymentAttempt.Status.PENDING)  # never applied

        # The poison event never blocked the good one from being resolved
        # in the very first run.
        self.assertEqual(good_event.processing_status, ProviderEvent.ProcessingStatus.PROCESSED)
        self.assertEqual(good_attempt.status, PaymentAttempt.Status.SUCCEEDED)
