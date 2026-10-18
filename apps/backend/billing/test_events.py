"""
BILL-WU-021 — event correlation, ordering and idempotent application
tests.
"""
from unittest.mock import patch

from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import User
from environments.models import Environment, EnvironmentMembership
from environments.tenancy_testing import TenantTestCase

from . import events
from .models import AmountOwed, BillingPeriod, PaymentAttempt, Plan, ProviderEvent, RecurringAgreement, Subscription


def _make_attempt(environment, subscription, plan, merchant_order_id, billing_period=None, status=PaymentAttempt.Status.PENDING):
    return PaymentAttempt.objects.create(
        environment=environment, subscription=subscription, billing_period=billing_period,
        merchant_order_id=merchant_order_id, amount_minor_units=plan.price_minor_units,
        currency=plan.currency, status=status,
    )


def _make_event(dedup_key, merchant_order_id, transaction_status, event_type="charge",
                 amount=None, currency=None, provider_transaction_id="txn-1", provider_order_id="ord-1",
                 agreement_ref="", mode="test"):
    return ProviderEvent.objects.create(
        dedup_key=dedup_key, mode=mode, event_type=event_type, transaction_status=transaction_status,
        provider_transaction_id=provider_transaction_id, provider_order_id=provider_order_id,
        signature_valid=True,
        redacted_payload={
            "merchant_order_id": merchant_order_id, "amount_minor_units": amount, "currency": currency,
            "agreement_ref": agreement_ref,
        },
    )


class SuccessActivatesCheckoutTests(TenantTestCase):
    """AC-BILL-021-1."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.subscription = Subscription.objects.create(environment=self.env_a, plan=self.plan, state=Subscription.State.TRIAL)
        self.attempt = _make_attempt(self.env_a, self.subscription, self.plan, "chk-ac1")

    def test_success_activates_the_subscription_with_a_30_day_period_and_an_agreement(self):
        event = _make_event(
            "dk-ac1", "chk-ac1", "SUCCESS", provider_transaction_id="txn-ac1", provider_order_id="ord-ac1",
            amount=self.plan.price_minor_units, currency=self.plan.currency, agreement_ref="agr_ac1",
        )

        events.apply(event)

        self.attempt.refresh_from_db()
        self.subscription.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(self.subscription.state, Subscription.State.ACTIVE)
        self.assertIsNotNone(self.attempt.billing_period_id)
        period = self.attempt.billing_period
        self.assertEqual(period.period_end - period.period_start, timezone.timedelta(days=30))
        self.assertIsNotNone(self.subscription.active_agreement_id)
        self.assertEqual(self.subscription.active_agreement.kashier_agreement_id, "agr_ac1")
        satisfied = AmountOwed.objects.get(billing_period=period)
        self.assertEqual(satisfied.status, AmountOwed.Status.SATISFIED)
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.PROCESSED)

    def test_order_paid_before_is_treated_as_already_succeeded(self):
        """Forward-compatible dispatch for BILL-WU-023 (status-lookup
        reconciliation, not built yet) — not a new charge."""
        event = _make_event(
            "dk-ac1-opb", "chk-ac1", "ORDER_PAID_BEFORE", provider_transaction_id="txn-ac1-opb",
            amount=self.plan.price_minor_units, currency=self.plan.currency,
        )

        events.apply(event)

        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.SUCCEEDED)


class RenewalSuccessTests(TenantTestCase):
    """Expected outcome's renewal branch (not individually AC-numbered,
    but part of this unit's documented behaviour) — the period is
    pre-created by BILL-WU-025 (simulated here, since that unit does not
    exist yet); applying SUCCESS only marks it satisfied."""

    def test_a_renewal_success_marks_the_pre_created_period_satisfied(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.ACTIVE)
        now = timezone.now()
        period = BillingPeriod.objects.create(
            environment=self.env_a, subscription=subscription, period_start=now, period_end=now + timezone.timedelta(days=30),
        )
        AmountOwed.objects.create(
            environment=self.env_a, billing_period=period, amount_minor_units=plan.price_minor_units,
            currency=plan.currency, status=AmountOwed.Status.OPEN,
        )
        attempt = _make_attempt(self.env_a, subscription, plan, "renewal-1", billing_period=period)

        event = _make_event(
            "dk-renewal-1", "renewal-1", "SUCCESS", provider_transaction_id="txn-renewal-1",
            amount=plan.price_minor_units, currency=plan.currency,
        )
        events.apply(event)

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(AmountOwed.objects.get(billing_period=period).status, AmountOwed.Status.SATISFIED)
        # No second period/agreement is created for a renewal.
        self.assertEqual(BillingPeriod.objects.filter(subscription=subscription).count(), 1)
        self.assertEqual(RecurringAgreement.objects.filter(subscription=subscription).count(), 0)


class IdempotentReapplicationTests(TenantTestCase):
    """AC-BILL-021-2."""

    def test_applying_the_same_event_twice_changes_nothing_the_second_time(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.TRIAL)
        attempt = _make_attempt(self.env_a, subscription, plan, "chk-ac2")
        event = _make_event(
            "dk-ac2", "chk-ac2", "SUCCESS", provider_transaction_id="txn-ac2",
            amount=plan.price_minor_units, currency=plan.currency, agreement_ref="agr_ac2",
        )

        events.apply(event)
        attempt.refresh_from_db()
        first_period_id = attempt.billing_period_id
        first_agreement_count = RecurringAgreement.objects.filter(subscription=subscription).count()

        event.refresh_from_db()  # bypasses receipt-time dedup: same row, re-fetched
        events.apply(event)

        attempt.refresh_from_db()
        self.assertEqual(attempt.billing_period_id, first_period_id)
        self.assertEqual(RecurringAgreement.objects.filter(subscription=subscription).count(), first_agreement_count)
        self.assertEqual(BillingPeriod.objects.filter(subscription=subscription).count(), 1)


class OutOfOrderSequenceTests(TenantTestCase):
    """AC-BILL-021-3."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.subscription = Subscription.objects.create(environment=self.env_a, plan=self.plan, state=Subscription.State.TRIAL)
        self.attempt = _make_attempt(self.env_a, self.subscription, self.plan, "chk-seq")

    def test_pending_then_success_ends_in_succeeded(self):
        pending_event = _make_event("dk-seq-pending", "chk-seq", "PENDING", provider_transaction_id="txn-seq")
        events.apply(pending_event)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.PENDING)

        success_event = _make_event(
            "dk-seq-success", "chk-seq", "SUCCESS", provider_transaction_id="txn-seq",
            amount=self.plan.price_minor_units, currency=self.plan.currency,
        )
        events.apply(success_event)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.SUCCEEDED)

    def test_success_then_pending_ends_in_succeeded_and_ignores_the_late_pending(self):
        success_event = _make_event(
            "dk-seq2-success", "chk-seq", "SUCCESS", provider_transaction_id="txn-seq2",
            amount=self.plan.price_minor_units, currency=self.plan.currency,
        )
        events.apply(success_event)

        late_pending = _make_event("dk-seq2-pending", "chk-seq", "PENDING", provider_transaction_id="txn-seq2")
        events.apply(late_pending)

        self.attempt.refresh_from_db()
        late_pending.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(late_pending.processing_status, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY)

    def test_success_then_failure_same_txn_ends_in_succeeded_and_the_failure_is_alerted_unapplied(self):
        success_event = _make_event(
            "dk-seq3-success", "chk-seq", "SUCCESS", provider_transaction_id="txn-seq3",
            amount=self.plan.price_minor_units, currency=self.plan.currency,
        )
        events.apply(success_event)

        late_failure = _make_event("dk-seq3-failure", "chk-seq", "FAILURE", provider_transaction_id="txn-seq3")
        events.apply(late_failure)

        self.attempt.refresh_from_db()
        late_failure.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(late_failure.processing_status, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY)
        self.assertTrue(late_failure.last_error)


class PayEventFailureTests(TenantTestCase):
    """AC-BILL-021-4."""

    def test_event_pay_status_failure_is_treated_as_failure(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.ACTIVE)
        now = timezone.now()
        period = BillingPeriod.objects.create(
            environment=self.env_a, subscription=subscription, period_start=now - timezone.timedelta(days=5),
            period_end=now + timezone.timedelta(days=25),
        )
        attempt = _make_attempt(self.env_a, subscription, plan, "renewal-pay", billing_period=period)

        event = _make_event("dk-pay-fail", "renewal-pay", "FAILURE", event_type="pay", provider_transaction_id="txn-pay")
        events.apply(event)

        attempt.refresh_from_db()
        subscription.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)
        self.assertEqual(subscription.state, Subscription.State.PAST_DUE)


class UncorrelatedEventTests(TenantTestCase):
    """AC-BILL-021-5."""

    def test_an_uncorrelated_merchant_order_id_changes_no_state(self):
        event = _make_event("dk-unc", "does-not-exist", "SUCCESS", provider_transaction_id="txn-unc")

        events.apply(event)

        event.refresh_from_db()
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY)
        self.assertIn("uncorrelated", event.last_error)
        self.assertEqual(PaymentAttempt.objects.count(), 0)
        self.assertEqual(Subscription.objects.filter(environment=self.env_a).count(), 0)


class AmountCurrencyMismatchTests(TenantTestCase):
    """AC-BILL-021-6."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.subscription = Subscription.objects.create(environment=self.env_a, plan=self.plan, state=Subscription.State.TRIAL)
        self.attempt = _make_attempt(self.env_a, self.subscription, self.plan, "chk-mismatch")

    def test_an_amount_mismatch_changes_no_state(self):
        event = _make_event(
            "dk-mismatch-amt", "chk-mismatch", "SUCCESS", provider_transaction_id="txn-mismatch-amt",
            amount=self.plan.price_minor_units + 1, currency=self.plan.currency,
        )
        events.apply(event)

        self.attempt.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.PENDING)
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY)
        self.assertIn("mismatch", event.last_error)

    def test_a_currency_mismatch_changes_no_state(self):
        event = _make_event(
            "dk-mismatch-cur", "chk-mismatch", "SUCCESS", provider_transaction_id="txn-mismatch-cur",
            amount=self.plan.price_minor_units, currency="USD",
        )
        events.apply(event)

        self.attempt.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.PENDING)
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY)
        self.assertIn("mismatch", event.last_error)


class RefundLikeEventsTests(TenantTestCase):
    """AC-BILL-021-8."""

    def test_a_refund_event_is_stored_and_not_applied(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        subscription = Subscription.objects.create(environment=self.env_a, plan=plan, state=Subscription.State.ACTIVE)
        attempt = _make_attempt(self.env_a, subscription, plan, "chk-refund", status=PaymentAttempt.Status.SUCCEEDED)

        event = _make_event("dk-refund", "chk-refund", "SUCCESS", event_type="refund", provider_transaction_id="txn-refund")
        events.apply(event)

        attempt.refresh_from_db()
        event.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.RECEIVED)
        self.assertTrue(event.last_error)


class CrashDuringApplicationTests(TransactionTestCase):
    """AC-BILL-021-7. Needs a real (non test-wrapped) transaction boundary
    — `TenantTestCase`'s base wraps every test in one outer atomic block,
    which would swallow the simulated crash's rollback semantics. Uses a
    minimal direct fixture instead (same pattern as
    `test_checkout.CheckoutProviderCallOutsideTransactionTests`).

    Uses `get_or_create` for the Plan row rather than `get`: a plain
    `TransactionTestCase` flushes every table after the test runs and
    does not restore a migration's seeded data (here,
    `billing.0002_seed_plans`'s three `Plan` rows) unless every
    `TransactionTestCase` in the whole run opts into
    `serialized_rollback`. Rather than depend on an unrelated,
    already-committed test module's `TransactionTestCase` doing that,
    this one creates its own Plan row if a prior flush (anywhere in the
    suite) already removed it — order-independent regardless of what
    else ran first."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="t", email="t-events-crash@example.com", phone="201020000099",
            password="Str0ng!Pass", is_active=True,
        )
        self.env = Environment.objects.create(owner=self.teacher, name="env")
        EnvironmentMembership.objects.create(user=self.teacher, environment=self.env, role=EnvironmentMembership.Role.OWNER)
        self.plan, _ = Plan.objects.get_or_create(
            key=Plan.Key.PLAN_1,
            defaults={"name": "Plan 1", "price_minor_units": 100000, "currency": "EGP", "max_students": 400},
        )
        self.subscription = Subscription.objects.create(environment=self.env, plan=self.plan, state=Subscription.State.TRIAL)
        self.attempt = _make_attempt(self.env, self.subscription, self.plan, "chk-crash")
        self.event = _make_event(
            "dk-crash", "chk-crash", "SUCCESS", provider_transaction_id="txn-crash",
            amount=self.plan.price_minor_units, currency=self.plan.currency,
        )

    def test_a_crash_between_state_change_and_event_marking_leaves_neither_applied(self):
        with self.assertRaises(RuntimeError):
            with patch.object(ProviderEvent.objects, "filter", side_effect=RuntimeError("simulated crash")):
                events.apply(self.event)

        self.attempt.refresh_from_db()
        self.event.refresh_from_db()
        self.subscription.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.PENDING)
        self.assertIsNone(self.attempt.billing_period_id)
        self.assertEqual(self.event.processing_status, ProviderEvent.ProcessingStatus.RECEIVED)
        self.assertEqual(self.subscription.state, Subscription.State.TRIAL)
        self.assertEqual(BillingPeriod.objects.filter(subscription=self.subscription).count(), 0)
        self.assertEqual(RecurringAgreement.objects.filter(subscription=self.subscription).count(), 0)
