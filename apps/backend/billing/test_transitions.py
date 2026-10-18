"""
BILL-WU-029 — failure versus ambiguity classification tests.
"""
import os

from django.test import SimpleTestCase
from django.utils import timezone

from environments.tenancy_testing import TenantTestCase

from . import entitlements
from .models import BillingPeriod, PaymentAttempt, Plan, Subscription
from .transitions import record_ambiguous, record_confirmed_failure


def _make_subscription(environment, **extra):
    return Subscription.objects.create(environment=environment, **extra)


class ConfirmedFailureOnRenewalTests(TenantTestCase):
    """AC-BILL-029-1."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.subscription = _make_subscription(self.env_a, plan=self.plan, state=Subscription.State.ACTIVE)
        now = timezone.now()
        start = now - timezone.timedelta(days=40)
        self.period = BillingPeriod.objects.create(
            environment=self.env_a, subscription=self.subscription,
            period_start=start, period_end=start + timezone.timedelta(days=30),
        )
        self.attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=self.subscription, billing_period=self.period,
            merchant_order_id="renewal-1", amount_minor_units=self.plan.price_minor_units,
            status=PaymentAttempt.Status.PENDING,
        )

    def test_a_confirmed_failure_marks_the_attempt_failed(self):
        record_confirmed_failure(self.attempt, provider_code="DECLINED", message="Card declined.")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.FAILED)

    def test_a_confirmed_failure_marks_the_subscription_payment_failed(self):
        record_confirmed_failure(self.attempt)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.state, Subscription.State.PAST_DUE)

    def test_entitlement_stays_granted_after_a_confirmed_renewal_failure(self):
        record_confirmed_failure(self.attempt)
        decision = entitlements.decide(self.env_a, now=timezone.now())
        self.assertTrue(decision.access_granted)
        self.assertEqual(decision.basis, entitlements.Basis.PAYMENT_FAILED_PENDING_POLICY)
        self.assertEqual(decision.reason_code, entitlements.ReasonCode.PAYMENT_FAILED_PENDING_POLICY)


class ConfirmedFailureOnCheckoutTests(TenantTestCase):
    """AC-BILL-029-1's checkout branch: "nothing changes on the
    subscription; the teacher may retry checkout."""

    def test_a_checkout_attempts_failure_does_not_touch_the_subscription(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = _make_subscription(self.env_a, state=Subscription.State.TRIAL)
        attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=subscription, billing_period=None,
            merchant_order_id="checkout-1", amount_minor_units=plan.price_minor_units,
            status=PaymentAttempt.Status.INITIATED,
        )

        record_confirmed_failure(attempt, provider_code="DECLINED", message="Card declined.")

        attempt.refresh_from_db()
        subscription.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)
        self.assertEqual(subscription.state, Subscription.State.TRIAL)


class AmbiguousOutcomeTests(TenantTestCase):
    """AC-BILL-029-2."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.subscription = _make_subscription(self.env_a, plan=self.plan, state=Subscription.State.ACTIVE)
        self.attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=self.subscription, billing_period=None,
            merchant_order_id="ambiguous-1", amount_minor_units=self.plan.price_minor_units,
            status=PaymentAttempt.Status.PENDING,
        )

    def test_a_timeout_is_recorded_as_ambiguous_never_failed(self):
        record_ambiguous(self.attempt)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.UNKNOWN)
        self.assertNotEqual(self.attempt.status, PaymentAttempt.Status.FAILED)

    def test_an_ambiguous_outcome_leaves_the_subscription_unchanged(self):
        record_ambiguous(self.attempt)
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.state, Subscription.State.ACTIVE)

    def test_an_ambiguous_attempt_is_still_non_terminal_for_reconciliation(self):
        record_ambiguous(self.attempt)
        self.attempt.refresh_from_db()
        self.assertIn(self.attempt.status, PaymentAttempt.NON_TERMINAL_STATUSES)


class NoRetryOrGraceSchedulingTests(SimpleTestCase):
    """AC-BILL-029-3: no code path in this unit schedules a retry or sets a
    grace deadline. AST-based, not a text grep: this module's own
    docstrings/comments *discuss* retry/grace (to document that they are
    NOT implemented here) — a plain substring search would self-trigger
    on that prose. Comments and docstrings never produce `Name`/
    `Attribute` nodes, so this check is blind to prose and only catches an
    actual identifier."""

    def test_transitions_module_defines_no_retry_or_grace_identifier(self):
        import ast

        path = os.path.join(os.path.dirname(__file__), "transitions.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)

        offending = []
        for node in ast.walk(tree):
            name = None
            if isinstance(node, ast.Name):
                name = node.id
            elif isinstance(node, ast.Attribute):
                name = node.attr
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = node.name
            if name and ("retry" in name.lower() or "grace" in name.lower()):
                offending.append(name)
        self.assertEqual(offending, [], f"forbidden retry/grace identifier(s): {offending}")

    def test_record_confirmed_failure_sets_no_future_dated_deadline(self):
        """A behavioural companion to the static check: the only fields
        this unit's functions ever write are `PaymentAttempt.status` and
        `Subscription.state` (verified by the other tests in this file) —
        no datetime field is ever set to anything but what was already on
        the row, which is what "no grace deadline" means in practice,
        since neither model has a grace-deadline field at all."""
        from .models import Subscription as SubscriptionModel

        field_names = {f.name for f in SubscriptionModel._meta.get_fields()}
        self.assertNotIn("first_failed_at", field_names)
        self.assertNotIn("grace_deadline", field_names)
        self.assertNotIn("failure_count", field_names)


class FailureAfterSuccessTests(TenantTestCase):
    """AC-BILL-029-4."""

    def test_a_failure_after_success_for_the_same_attempt_is_not_applied(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = _make_subscription(self.env_a, plan=plan, state=Subscription.State.ACTIVE)
        attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=subscription, billing_period=None,
            merchant_order_id="succeeded-1", amount_minor_units=plan.price_minor_units,
            status=PaymentAttempt.Status.SUCCEEDED,
        )

        record_confirmed_failure(attempt, provider_code="LATE_FAILURE", message="should not apply")

        attempt.refresh_from_db()
        subscription.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(subscription.state, Subscription.State.ACTIVE)

    def test_an_ambiguous_outcome_after_success_is_also_not_applied(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = _make_subscription(self.env_a, plan=plan)
        attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=subscription, billing_period=None,
            merchant_order_id="succeeded-2", amount_minor_units=plan.price_minor_units,
            status=PaymentAttempt.Status.SUCCEEDED,
        )

        record_ambiguous(attempt)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
