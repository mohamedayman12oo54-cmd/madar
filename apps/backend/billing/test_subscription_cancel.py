"""
BILL-WU-028 — cancel-at-period-end service and renewal-race tests.

Named `test_subscription_cancel` (not `test_cancel`) so this module sorts
alphabetically AFTER `test_checkout.py` in Django's test-discovery order:
`test_checkout.py`'s own `TransactionTestCase`
(`CheckoutProviderCallOutsideTransactionTests`, pre-existing, BILL-WU-019)
assumes the `Plan` catalog is still migration-seeded and does not defend
itself with `get_or_create` — it has only ever been safe because it was
alphabetically first among this app's `TransactionTestCase` classes, which
Django runs as a separate, later bin, in discovery order. A module
sorting ahead of it would flush that seed data first and break it — not
something to fix by editing that unrelated, already-VERIFIED file.

Uses a minimal direct `TransactionTestCase` fixture (same pattern as
`test_process_billing_renewals.py`'s `_Fixture`) rather than
`TenantTestCase`, because the race tests call `cancel_subscription` and
`claim_due_subscription` directly, back to back, inside one test — each
takes its own real (non test-wrapped) transaction, which `TenantTestCase`'s
outer atomic wrapper would mask.
"""
from datetime import timedelta
from unittest import mock

from django.test import TransactionTestCase
from django.utils import timezone

from accounts.models import User
from environments.models import Environment, EnvironmentMembership

from . import entitlements, events
from .management.commands.process_billing_renewals import claim_due_subscription
from .models import AmountOwed, BillingPeriod, PaymentAttempt, Plan, RecurringAgreement, Subscription
from .providers import FakePaymentProvider
from .services import cancel_subscription


class _Fixture(TransactionTestCase):
    """Uses `get_or_create` for the Plan row rather than `get` — same
    reasoning as `test_events.CrashDuringApplicationTests`: a
    `TransactionTestCase` flushes every table after the test and does not
    reliably restore migration-seeded rows (`billing.0002_seed_plans`'s
    three `Plan` rows) across the whole run. This fixture creates its own
    Plan row if a prior flush already removed it — order-independent
    regardless of what else ran first."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="t", email=f"t-028-{self._testMethodName}@example.com",
            phone="201020000222", password="Str0ng!Pass", is_active=True,
        )
        self.env = Environment.objects.create(owner=self.teacher, name="env")
        EnvironmentMembership.objects.create(user=self.teacher, environment=self.env, role=EnvironmentMembership.Role.OWNER)
        self.plan, _ = Plan.objects.get_or_create(
            key=Plan.Key.PLAN_1,
            defaults={"name": "Plan 1", "price_minor_units": 100000, "currency": "EGP", "max_students": 400},
        )

    def make_active_subscription(self):
        now = timezone.now()
        subscription = Subscription.objects.create(
            environment=self.env, plan=self.plan, state=Subscription.State.ACTIVE,
            current_period_start=now - timedelta(days=5), current_period_end=now + timedelta(days=25),
        )
        period = BillingPeriod.objects.create(
            environment=self.env, subscription=subscription,
            period_start=now - timedelta(days=5), period_end=now + timedelta(days=25),
        )
        PaymentAttempt.objects.create(
            environment=self.env, subscription=subscription, billing_period=period,
            merchant_order_id=f"chk-{subscription.pk}", amount_minor_units=self.plan.price_minor_units,
            currency=self.plan.currency, status=PaymentAttempt.Status.SUCCEEDED,
        )
        agreement = RecurringAgreement.objects.create(
            environment=self.env, subscription=subscription, card_token="tok_abc",
            kashier_agreement_id=f"agr-{subscription.pk}", mode=RecurringAgreement.Mode.TEST,
        )
        subscription.active_agreement = agreement
        subscription.save(update_fields=["active_agreement"])
        return subscription, period

    def make_due_subscription(self, environment=None):
        """A subscription whose current period has already ended —
        eligible for `claim_due_subscription` (mirrors
        `test_process_billing_renewals.py`'s helper of the same name)."""
        environment = environment or self.env
        now = timezone.now()
        subscription = Subscription.objects.create(
            environment=environment, plan=self.plan, state=Subscription.State.ACTIVE,
            current_period_start=now - timedelta(days=30), current_period_end=now,
        )
        BillingPeriod.objects.create(
            environment=environment, subscription=subscription,
            period_start=now - timedelta(days=30), period_end=now,
        )
        agreement = RecurringAgreement.objects.create(
            environment=environment, subscription=subscription, card_token="tok_abc",
            kashier_agreement_id=f"agr-{subscription.pk}", mode=RecurringAgreement.Mode.TEST,
        )
        subscription.active_agreement = agreement
        subscription.save(update_fields=["active_agreement"])
        return subscription


class AccessThroughPeriodEndTests(_Fixture):
    """AC-BILL-028-1 (frozen-clock): access remains granted until the
    current period end and ends at period end, regardless of the cancel
    flag — `entitlements.decide` already derives this purely from period
    windows and successful attempts (BILL-WU-010), so cancelling never
    needs to flip any extra access-controlling field."""

    def test_access_remains_granted_until_period_end_and_ends_at_period_end(self):
        subscription, period = self.make_active_subscription()
        cancel_subscription(self.env)

        just_before = period.period_end - timedelta(seconds=1)
        decision_before = entitlements.decide(self.env, now=just_before)
        self.assertTrue(decision_before.access_granted)
        self.assertEqual(decision_before.basis, entitlements.Basis.CANCELLED_BUT_PAID_THROUGH)

        at_end = period.period_end
        decision_at_end = entitlements.decide(self.env, now=at_end)
        self.assertFalse(decision_at_end.access_granted)
        self.assertEqual(decision_at_end.reason_code, entitlements.ReasonCode.PERIOD_ENDED)


class CancelBeforeClaimTests(_Fixture):
    """AC-BILL-028-2."""

    def test_cancel_committed_before_the_renewal_claim_results_in_no_attempt_and_no_charge(self):
        subscription = self.make_due_subscription()
        now = timezone.now()

        result = cancel_subscription(self.env)
        self.assertTrue(result.cancel_at_period_end)
        self.assertFalse(result.renewal_already_in_progress)

        attempt = claim_due_subscription(subscription.pk, now)
        self.assertIsNone(attempt)
        self.assertEqual(PaymentAttempt.objects.filter(subscription=subscription).count(), 0)


class ClaimBeforeCancelTests(_Fixture):
    """AC-BILL-028-3."""

    def test_claim_committed_first_then_cancel_reports_renewal_already_in_progress(self):
        subscription = self.make_due_subscription()
        now = timezone.now()

        attempt = claim_due_subscription(subscription.pk, now)
        self.assertIsNotNone(attempt)

        result = cancel_subscription(self.env)
        self.assertTrue(result.cancel_at_period_end)
        self.assertTrue(result.renewal_already_in_progress)
        self.assertEqual(result.renewal_attempt_status, PaymentAttempt.Status.INITIATED)

    def test_if_the_in_flight_charge_then_succeeds_access_extends_through_that_period_with_no_second_charge(self):
        subscription = self.make_due_subscription()
        now = timezone.now()
        old_end = subscription.current_period_end

        attempt = claim_due_subscription(subscription.pk, now)
        cancel_subscription(self.env)

        provider = FakePaymentProvider()
        result = provider.charge_saved_agreement(attempt, "tok_abc")
        events.apply_success(
            attempt, provider_transaction_id=result.provider_transaction_id,
            provider_order_id=result.provider_order_id,
        )

        subscription.refresh_from_db()
        self.assertEqual(subscription.current_period_end, old_end + timedelta(days=30))
        self.assertTrue(subscription.cancel_at_period_end)  # still set — applies at the NEW period's end
        self.assertEqual(PaymentAttempt.objects.filter(subscription=subscription).count(), 1)

        # A later claim call (the next worker run) sees the flag and never
        # creates a second attempt for a further period.
        second_claim = claim_due_subscription(subscription.pk, subscription.current_period_end)
        self.assertIsNone(second_claim)


class NoDeadlockNoDoubleAttemptTests(_Fixture):
    """AC-BILL-028-4. Both `cancel_subscription` and
    `claim_due_subscription` take exactly one lock — the Subscription
    row — before anything else, and neither acquires a second lock before
    releasing or committing it (see `services.cancel_subscription`'s
    module-level note). With only one lock in play, a genuine deadlock
    between the two paths is structurally impossible, so the race is
    exercised sequentially in both orderings (same convention as
    `test_process_billing_renewals.ConcurrentClaimTests`), each run on its
    own Environment/Subscription (one per Environment, BILL-WU-008's
    OneToOneField) so the two orderings don't interfere with each other."""

    def test_both_orderings_run_cleanly_with_no_deadlock_and_at_most_one_attempt(self):
        env_2 = Environment.objects.create(owner=self.teacher, name="env-2")
        EnvironmentMembership.objects.create(user=self.teacher, environment=env_2, role=EnvironmentMembership.Role.OWNER)

        sub_1 = self.make_due_subscription(self.env)
        sub_2 = self.make_due_subscription(env_2)
        now = timezone.now()

        # Ordering A: cancel first.
        cancel_subscription(self.env)
        attempt_a = claim_due_subscription(sub_1.pk, now)
        self.assertIsNone(attempt_a)
        self.assertEqual(PaymentAttempt.objects.filter(subscription=sub_1).count(), 0)

        # Ordering B: claim first (a different Environment/Subscription).
        attempt_b = claim_due_subscription(sub_2.pk, now)
        cancel_subscription(env_2)
        self.assertIsNotNone(attempt_b)
        self.assertEqual(PaymentAttempt.objects.filter(subscription=sub_2).count(), 1)


class NoRefundNoDataDeletionTests(_Fixture):
    """AC-BILL-028-5."""

    def test_cancelling_creates_no_refund_and_deletes_no_data(self):
        subscription, period = self.make_active_subscription()
        attempts_before = PaymentAttempt.objects.filter(subscription=subscription).count()
        amounts_before = AmountOwed.objects.filter(billing_period=period).count()
        periods_before = BillingPeriod.objects.filter(subscription=subscription).count()

        cancel_subscription(self.env)

        self.assertEqual(PaymentAttempt.objects.filter(subscription=subscription).count(), attempts_before)
        self.assertEqual(AmountOwed.objects.filter(billing_period=period).count(), amounts_before)
        self.assertEqual(BillingPeriod.objects.filter(subscription=subscription).count(), periods_before)
        # No new SUCCEEDED attempt was reversed/refunded — the original
        # attempt's status is untouched.
        self.assertEqual(
            PaymentAttempt.objects.filter(subscription=subscription, status=PaymentAttempt.Status.SUCCEEDED).count(),
            1,
        )


class IdempotentCancelTests(_Fixture):
    def test_a_repeat_cancel_call_returns_the_same_state(self):
        self.make_active_subscription()

        result_1 = cancel_subscription(self.env)
        result_2 = cancel_subscription(self.env)

        self.assertEqual(result_1, result_2)
