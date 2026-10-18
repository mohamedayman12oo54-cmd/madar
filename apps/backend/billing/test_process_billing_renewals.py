"""
BILL-WU-025 — renewal claim, crash safety and cancellation skip tests.
"""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import connection
from django.test import TransactionTestCase, override_settings
from django.utils import timezone

from accounts.models import User
from environments.models import Environment, EnvironmentMembership

from .management.commands.process_billing_renewals import claim_due_subscription
from .models import AmountOwed, BillingPeriod, PaymentAttempt, Plan, RecurringAgreement, Subscription
from .providers import FakePaymentProvider


def run_renewals(*args):
    out = StringIO()
    call_command("process_billing_renewals", *args, stdout=out)
    return out.getvalue()


class _Fixture(TransactionTestCase):
    """Every renewal scenario needs a real (non test-wrapped) transaction
    boundary — the concurrency/crash tests specifically, and consistency
    with the other `TransactionTestCase` suites in this app's billing
    tests. Minimal direct fixture (no shared `TenantTestCase` base)."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="t", email=f"t-025-{self._testMethodName}@example.com",
            phone="201020000111", password="Str0ng!Pass", is_active=True,
        )
        self.env = Environment.objects.create(owner=self.teacher, name="env")
        EnvironmentMembership.objects.create(user=self.teacher, environment=self.env, role=EnvironmentMembership.Role.OWNER)
        self.plan, _ = Plan.objects.get_or_create(
            key=Plan.Key.PLAN_1,
            defaults={"name": "Plan 1", "price_minor_units": 100000, "currency": "EGP", "max_students": 400},
        )

    def make_due_subscription(self, *, cancel_at_period_end=False):
        now = timezone.now()
        subscription = Subscription.objects.create(
            environment=self.env, plan=self.plan, state=Subscription.State.ACTIVE,
            cancel_at_period_end=cancel_at_period_end,
            current_period_start=now - timedelta(days=30), current_period_end=now,
        )
        BillingPeriod.objects.create(
            environment=self.env, subscription=subscription,
            period_start=now - timedelta(days=30), period_end=now,
        )
        agreement = RecurringAgreement.objects.create(
            environment=self.env, subscription=subscription, card_token="tok_abc",
            kashier_agreement_id="agr_abc", mode=RecurringAgreement.Mode.TEST,
        )
        subscription.active_agreement = agreement
        subscription.save(update_fields=["active_agreement"])
        return subscription


class OneAttemptOneChargePerPeriodTests(_Fixture):
    """AC-BILL-025-1."""

    def test_a_due_subscription_gets_exactly_one_attempt_one_charge_and_extends_access_30_days(self):
        subscription = self.make_due_subscription()
        old_end = subscription.current_period_end
        provider = FakePaymentProvider()

        with mock.patch(
            "billing.management.commands.process_billing_renewals.get_payment_provider", return_value=provider
        ), mock.patch.object(FakePaymentProvider, "charge_saved_agreement", wraps=provider.charge_saved_agreement) as charge_mock:
            out = run_renewals()

        charge_mock.assert_called_once()
        self.assertEqual(PaymentAttempt.objects.filter(subscription=subscription).count(), 1)
        attempt = PaymentAttempt.objects.get(subscription=subscription)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        subscription.refresh_from_db()
        self.assertEqual(subscription.current_period_end, old_end + timedelta(days=30))
        self.assertEqual(AmountOwed.objects.get(billing_period=attempt.billing_period).status, AmountOwed.Status.SATISFIED)
        self.assertIn("1 charged", out)


class ConcurrentClaimTests(_Fixture):
    """AC-BILL-025-2. Sequential calls to the claim function exercise the
    exact same re-check-under-lock code path a real second worker would
    hit after the first's transaction commits (the realistic race: both
    see the same due subscription before either resolves it)."""

    def test_two_concurrent_claims_produce_exactly_one_attempt(self):
        subscription = self.make_due_subscription()
        now = timezone.now()

        attempt_a = claim_due_subscription(subscription.pk, now)
        attempt_b = claim_due_subscription(subscription.pk, now)

        self.assertIsNotNone(attempt_a)
        self.assertIsNone(attempt_b)  # loses the race: renewal_due is now false
        self.assertEqual(PaymentAttempt.objects.filter(subscription=subscription).count(), 1)
        self.assertEqual(BillingPeriod.objects.filter(subscription=subscription).count(), 2)  # original + new

    def test_two_full_runs_produce_exactly_one_charge_call(self):
        subscription = self.make_due_subscription()
        provider = FakePaymentProvider()

        with mock.patch(
            "billing.management.commands.process_billing_renewals.get_payment_provider", return_value=provider
        ), mock.patch.object(FakePaymentProvider, "charge_saved_agreement", wraps=provider.charge_saved_agreement) as charge_mock:
            run_renewals()
            run_renewals()  # a second worker/run arriving right after

        charge_mock.assert_called_once()


class CrashAfterChargeTests(_Fixture):
    """AC-BILL-025-3."""

    def test_a_crash_after_charge_and_before_persist_leads_to_unknown_with_no_second_charge(self):
        subscription = self.make_due_subscription()
        provider = FakePaymentProvider()

        with mock.patch(
            "billing.management.commands.process_billing_renewals.get_payment_provider", return_value=provider
        ), mock.patch.object(FakePaymentProvider, "charge_saved_agreement", wraps=provider.charge_saved_agreement) as charge_mock, \
           mock.patch("billing.management.commands.process_billing_renewals.events.apply_success", side_effect=RuntimeError("simulated crash")):
            with self.assertRaises(RuntimeError):
                run_renewals()

        charge_mock.assert_called_once()
        attempt = PaymentAttempt.objects.get(subscription=subscription)
        self.assertEqual(attempt.status, PaymentAttempt.Status.INITIATED)  # never persisted

        # Back-date it so the next run's stale sweep treats it as stale
        # (real time elapsed in this test is near-zero otherwise).
        PaymentAttempt.objects.filter(pk=attempt.pk).update(updated_at=timezone.now() - timedelta(minutes=45))

        with mock.patch(
            "billing.management.commands.process_billing_renewals.get_payment_provider", return_value=provider
        ), mock.patch.object(FakePaymentProvider, "charge_saved_agreement", wraps=provider.charge_saved_agreement) as charge_mock_2:
            run_renewals("--requeue-stale-minutes", "15")

        charge_mock_2.assert_not_called()  # no second charge
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.UNKNOWN)


class ConfirmedFailureTests(_Fixture):
    """AC-BILL-025-4."""

    def test_a_confirmed_failure_is_recorded_and_never_retried(self):
        subscription = self.make_due_subscription()
        provider = FakePaymentProvider()

        with mock.patch("billing.management.commands.process_billing_renewals.get_payment_provider", return_value=provider):
            # Scripting requires knowing the generated merchant_order_id —
            # script it on the attempt AFTER the claim step instead, via
            # a wrapper that intercepts the attempt's own order id.
            original_charge = FakePaymentProvider.charge_saved_agreement

            def scripted_charge(self, attempt, agreement_ref):
                self.script_outcome(attempt.merchant_order_id, "failed")
                return original_charge(self, attempt, agreement_ref)

            with mock.patch.object(FakePaymentProvider, "charge_saved_agreement", scripted_charge):
                run_renewals()

        attempt = PaymentAttempt.objects.get(subscription=subscription)
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)
        subscription.refresh_from_db()
        self.assertEqual(subscription.state, Subscription.State.PAST_DUE)

        # A second run never retries: the subscription is no longer
        # `active` (PAST_DUE), so it is not even a candidate.
        with mock.patch(
            "billing.management.commands.process_billing_renewals.get_payment_provider", return_value=provider
        ), mock.patch.object(FakePaymentProvider, "charge_saved_agreement") as charge_mock:
            run_renewals()
        charge_mock.assert_not_called()
        self.assertEqual(PaymentAttempt.objects.filter(subscription=subscription).count(), 1)


class CancellationSkipTests(_Fixture):
    """AC-BILL-025-5."""

    def test_a_subscription_with_cancel_at_period_end_is_never_charged(self):
        subscription = self.make_due_subscription(cancel_at_period_end=True)
        provider = FakePaymentProvider()

        with mock.patch(
            "billing.management.commands.process_billing_renewals.get_payment_provider", return_value=provider
        ), mock.patch.object(FakePaymentProvider, "charge_saved_agreement") as charge_mock:
            run_renewals()

        charge_mock.assert_not_called()
        self.assertEqual(PaymentAttempt.objects.filter(subscription=subscription).count(), 0)


class LiveModeKillSwitchTests(_Fixture):
    """AC-BILL-025-6."""

    def test_live_mode_with_the_kill_switch_off_charges_nothing(self):
        subscription = self.make_due_subscription()
        provider = FakePaymentProvider()

        with override_settings(KASHIER_MODE="live", BILLING_RENEWALS_LIVE_ENABLED=False), mock.patch(
            "billing.management.commands.process_billing_renewals.get_payment_provider", return_value=provider
        ), mock.patch.object(FakePaymentProvider, "charge_saved_agreement") as charge_mock:
            out = run_renewals()

        charge_mock.assert_not_called()
        self.assertEqual(PaymentAttempt.objects.filter(subscription=subscription).count(), 0)
        self.assertIn("disabled", out)


class NoChargeInsideTransactionTests(_Fixture):
    """AC-BILL-025-7."""

    def test_the_charge_call_happens_outside_any_transaction(self):
        subscription = self.make_due_subscription()
        provider = FakePaymentProvider()
        captured = {}
        original = FakePaymentProvider.charge_saved_agreement

        def spy(self, attempt, agreement_ref):
            captured["in_atomic_block"] = connection.in_atomic_block
            return original(self, attempt, agreement_ref)

        with mock.patch(
            "billing.management.commands.process_billing_renewals.get_payment_provider", return_value=provider
        ), mock.patch.object(FakePaymentProvider, "charge_saved_agreement", spy):
            run_renewals()

        self.assertIn("in_atomic_block", captured)
        self.assertFalse(captured["in_atomic_block"])
