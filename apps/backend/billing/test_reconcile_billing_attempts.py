"""
BILL-WU-023 — reconciliation and duplicate-charge guard tests.
"""
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import IntegrityError
from django.test import TransactionTestCase
from django.utils import timezone

from environments.tenancy_testing import TenantTestCase

from . import events
from .management.commands.reconcile_billing_attempts import _reconcile_one
from .models import AmountOwed, BillingPeriod, PaymentAttempt, Plan, Subscription
from .providers import FakePaymentProvider
from .services import start_checkout
from .transitions import record_confirmed_failure


def run_reconciler(*args):
    out = StringIO()
    call_command("reconcile_billing_attempts", *args, stdout=out)
    return out.getvalue()


def _make_old_renewal_attempt(environment, subscription, plan, merchant_order_id, status=PaymentAttempt.Status.UNKNOWN, age_minutes=30):
    now = timezone.now()
    period = BillingPeriod.objects.create(
        environment=environment, subscription=subscription, period_start=now, period_end=now + timedelta(days=30),
    )
    AmountOwed.objects.create(
        environment=environment, billing_period=period, amount_minor_units=plan.price_minor_units,
        currency=plan.currency, status=AmountOwed.Status.OPEN,
    )
    attempt = PaymentAttempt.objects.create(
        environment=environment, subscription=subscription, billing_period=period,
        merchant_order_id=merchant_order_id, amount_minor_units=plan.price_minor_units,
        currency=plan.currency, status=status,
    )
    PaymentAttempt.objects.filter(pk=attempt.pk).update(created_at=now - timedelta(minutes=age_minutes))
    attempt.refresh_from_db()
    return attempt, period


def _make_old_checkout_attempt(environment, subscription, plan, merchant_order_id, status=PaymentAttempt.Status.PENDING, age_minutes=30):
    attempt = PaymentAttempt.objects.create(
        environment=environment, subscription=subscription, billing_period=None,
        merchant_order_id=merchant_order_id, amount_minor_units=plan.price_minor_units,
        currency=plan.currency, status=status,
    )
    PaymentAttempt.objects.filter(pk=attempt.pk).update(
        created_at=timezone.now() - timedelta(minutes=age_minutes)
    )
    attempt.refresh_from_db()
    return attempt


class UnknownRenewalResolvedAsPaidTests(TenantTestCase):
    """AC-BILL-023-1."""

    def test_an_unknown_renewal_attempt_resolved_as_paid_marks_the_period_paid_with_no_second_charge(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.ACTIVE)
        attempt, period = _make_old_renewal_attempt(self.env_a, subscription, plan, "rec-ac1")

        provider = FakePaymentProvider()
        provider.script_outcome("rec-ac1", "succeeded")
        with mock.patch("billing.management.commands.reconcile_billing_attempts.get_payment_provider", return_value=provider), \
             mock.patch.object(FakePaymentProvider, "charge_saved_agreement") as charge_mock:
            out = run_reconciler("--min-age-minutes", "10")

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(AmountOwed.objects.get(billing_period=period).status, AmountOwed.Status.SATISFIED)
        charge_mock.assert_not_called()  # lookup only — no second charge attempted
        self.assertIn("1 resolved", out)


class DuplicateChargeGuardTests(TenantTestCase):
    """AC-BILL-023-2: while an attempt for a period is unresolved, no new
    charge attempt for that period can be created (the DB constraint
    from BILL-WU-008). A renewal-charge-creation *service* doesn't exist
    yet (BILL-WU-025, out of scope here) to additionally test the
    "service check" half of this AC's wording."""

    def test_a_second_non_terminal_attempt_for_the_same_period_is_rejected(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.ACTIVE)
        attempt, period = _make_old_renewal_attempt(self.env_a, subscription, plan, "rec-ac2", status=PaymentAttempt.Status.PENDING)

        with self.assertRaises(IntegrityError):
            PaymentAttempt.objects.create(
                environment=self.env_a, subscription=subscription, billing_period=period,
                merchant_order_id="rec-ac2-second", amount_minor_units=plan.price_minor_units,
                currency=plan.currency, status=PaymentAttempt.Status.INITIATED,
            )


class InconclusiveLookupTests(TenantTestCase):
    """AC-BILL-023-3."""

    def test_an_inconclusive_lookup_leaves_state_unchanged(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.ACTIVE)
        attempt, period = _make_old_renewal_attempt(self.env_a, subscription, plan, "rec-ac3")

        provider = FakePaymentProvider()
        provider.script_outcome("rec-ac3", "pending")
        with mock.patch("billing.management.commands.reconcile_billing_attempts.get_payment_provider", return_value=provider):
            out = run_reconciler("--min-age-minutes", "10")

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.UNKNOWN)
        self.assertEqual(AmountOwed.objects.get(billing_period=period).status, AmountOwed.Status.OPEN)
        subscription.refresh_from_db()
        self.assertEqual(subscription.state, Subscription.State.ACTIVE)
        self.assertIn("1 still unresolved", out)


class AbandonedCheckoutTests(TenantTestCase):
    """AC-BILL-023-4."""

    def test_an_abandoned_checkout_attempt_becomes_terminal_and_a_new_checkout_is_then_allowed(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.TRIAL)
        attempt = _make_old_checkout_attempt(
            self.env_a, subscription, plan, "rec-ac4", age_minutes=25 * 60,
        )

        provider = FakePaymentProvider()
        provider.script_outcome("rec-ac4", "pending")  # no usable provider record
        with mock.patch("billing.management.commands.reconcile_billing_attempts.get_payment_provider", return_value=provider):
            out = run_reconciler("--min-age-minutes", "10", "--abandon-age-minutes", str(24 * 60))

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)
        self.assertIn("1 abandoned", out)

        # A new checkout is allowed now — not blocked by the abandoned one.
        with mock.patch("billing.management.commands.reconcile_billing_attempts.get_payment_provider", return_value=provider):
            new_attempt, session_url = start_checkout(self.env_a, Plan.Key.PLAN_1, "https://app.example.com/return")
        self.assertNotEqual(new_attempt.pk, attempt.pk)
        self.assertTrue(session_url)

    def test_a_not_yet_old_enough_checkout_attempt_is_left_unresolved_not_abandoned(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.TRIAL)
        attempt = _make_old_checkout_attempt(self.env_a, subscription, plan, "rec-ac4b", age_minutes=20)

        provider = FakePaymentProvider()
        provider.script_outcome("rec-ac4b", "pending")
        with mock.patch("billing.management.commands.reconcile_billing_attempts.get_payment_provider", return_value=provider):
            run_reconciler("--min-age-minutes", "10", "--abandon-age-minutes", str(24 * 60))

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.PENDING)


class ConcurrentReconcilersTests(TransactionTestCase):
    """AC-BILL-023-5. Needs a real (non test-wrapped) transaction
    boundary — `TenantTestCase`'s base wraps every test in one outer
    atomic block, which would mask the self-contained claim mechanism
    under test here. Minimal direct fixture (same pattern as other
    `TransactionTestCase` classes in this app's billing tests)."""

    def setUp(self):
        from accounts.models import User
        from environments.models import Environment, EnvironmentMembership

        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="t", email="t-023-concurrent@example.com", phone="201020000066",
            password="Str0ng!Pass", is_active=True,
        )
        self.env = Environment.objects.create(owner=self.teacher, name="env")
        EnvironmentMembership.objects.create(user=self.teacher, environment=self.env, role=EnvironmentMembership.Role.OWNER)
        self.plan, _ = Plan.objects.get_or_create(
            key=Plan.Key.PLAN_1,
            defaults={"name": "Plan 1", "price_minor_units": 100000, "currency": "EGP", "max_students": 400},
        )
        self.subscription = Subscription.objects.create(environment=self.env, plan=self.plan, state=Subscription.State.ACTIVE)

    def test_two_concurrent_reconcilers_apply_a_success_outcome_once(self):
        attempt, period = _make_old_renewal_attempt(self.env, self.subscription, self.plan, "rec-ac5-success")
        provider = FakePaymentProvider()
        provider.script_outcome("rec-ac5-success", "succeeded")
        abandon_before = timezone.now() - timedelta(days=1)

        # Both "reconcilers" fetched the SAME non-terminal attempt before
        # either resolved it — the realistic race. Only the first call's
        # conditional UPDATE (inside `events.apply_success`) can match.
        outcome_a = _reconcile_one(attempt, provider, abandon_before)
        outcome_b = _reconcile_one(attempt, provider, abandon_before)

        self.assertEqual(outcome_a, "resolved")
        self.assertEqual(outcome_b, "resolved")  # also returns "resolved" (lookup succeeded); the SECOND application is the no-op
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        # Exactly one agreement/period bookkeeping effect — not created twice.
        self.assertEqual(AmountOwed.objects.filter(billing_period=period, status=AmountOwed.Status.SATISFIED).count(), 1)

    def test_two_concurrent_reconcilers_apply_a_failure_outcome_once(self):
        attempt, period = _make_old_renewal_attempt(self.env, self.subscription, self.plan, "rec-ac5-failure")
        provider = FakePaymentProvider()
        provider.script_outcome("rec-ac5-failure", "failed")
        abandon_before = timezone.now() - timedelta(days=1)

        record_confirmed_failure(attempt, provider_code="first-caller")
        attempt.refresh_from_db()
        outcome_b = _reconcile_one(attempt, provider, abandon_before)

        self.assertEqual(outcome_b, "resolved")
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.state, Subscription.State.PAST_DUE)
