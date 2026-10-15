"""
BILL-WU-008 — persistence/integrity-constraint tests for the billing module.

These exercise real PostgreSQL constraints (partial unique indexes, CHECK
constraints), not just Python-level validation, so they must run against
PostgreSQL (see apps/backend/POSTGRESQL.md) — SQLite silently ignores some
of what's asserted here.
"""
import ast
import os

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from environments.models import Environment

from .models import (
    AmountOwed,
    BillingPeriod,
    Plan,
    PaymentAttempt,
    ProviderEvent,
    RecurringAgreement,
    Subscription,
)


def make_environment(owner_username="teacher-billwu008"):
    owner = User.objects.create(username=owner_username, role=User.Role.TEACHER)
    return Environment.objects.create(owner=owner, name="Env for BILL-WU-008 tests")


def make_subscription(environment=None):
    environment = environment or make_environment()
    return Subscription.objects.create(environment=environment)


def make_billing_period(subscription=None, start=None):
    subscription = subscription or make_subscription()
    start = start or timezone.now()
    return BillingPeriod.objects.create(
        environment=subscription.environment,
        subscription=subscription, period_start=start, period_end=start + timezone.timedelta(days=30)
    )


class SubscriptionCardinalityTests(TestCase):
    """AC-BILL-008-1."""

    def test_two_subscriptions_for_one_environment_raise_integrity_error(self):
        environment = make_environment()
        Subscription.objects.create(environment=environment)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Subscription.objects.create(environment=environment)

    def test_two_subscriptions_for_different_environments_both_succeed(self):
        Subscription.objects.create(environment=make_environment("teacher-a"))
        Subscription.objects.create(environment=make_environment("teacher-b"))
        self.assertEqual(Subscription.objects.count(), 2)


class BillingPeriodUniquenessTests(TestCase):
    """AC-BILL-008-5."""

    def test_two_periods_with_same_subscription_and_start_are_rejected(self):
        subscription = make_subscription()
        start = timezone.now()
        BillingPeriod.objects.create(
            environment=subscription.environment,
            subscription=subscription, period_start=start, period_end=start + timezone.timedelta(days=30)
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BillingPeriod.objects.create(
                    environment=subscription.environment,
                    subscription=subscription, period_start=start, period_end=start + timezone.timedelta(days=30)
                )

    def test_same_subscription_different_start_succeeds(self):
        subscription = make_subscription()
        start1 = timezone.now()
        start2 = start1 + timezone.timedelta(days=30)
        BillingPeriod.objects.create(
            environment=subscription.environment, subscription=subscription, period_start=start1, period_end=start2
        )
        BillingPeriod.objects.create(
            environment=subscription.environment,
            subscription=subscription, period_start=start2, period_end=start2 + timezone.timedelta(days=30)
        )
        self.assertEqual(BillingPeriod.objects.filter(subscription=subscription).count(), 2)


class PaymentAttemptIntegrityTests(TestCase):
    """AC-BILL-008-2 and AC-BILL-008-4."""

    def _attempt(self, environment, subscription, billing_period, status, merchant_order_id, **extra):
        return PaymentAttempt.objects.create(
            environment=environment,
            subscription=subscription,
            billing_period=billing_period,
            status=status,
            merchant_order_id=merchant_order_id,
            amount_minor_units=100000,
            **extra,
        )

    def test_two_non_terminal_attempts_for_same_period_raise_integrity_error(self):
        environment = make_environment()
        period = make_billing_period(make_subscription(environment))
        self._attempt(environment, period.subscription, period, PaymentAttempt.Status.PENDING, "order-1")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._attempt(environment, period.subscription, period, PaymentAttempt.Status.INITIATED, "order-2")

    def test_a_second_attempt_after_the_first_is_terminal_is_allowed(self):
        environment = make_environment()
        period = make_billing_period(make_subscription(environment))
        first = self._attempt(environment, period.subscription, period, PaymentAttempt.Status.PENDING, "order-3")
        first.status = PaymentAttempt.Status.FAILED
        first.save(update_fields=["status"])

        second = self._attempt(environment, period.subscription, period, PaymentAttempt.Status.PENDING, "order-4")
        self.assertEqual(
            PaymentAttempt.objects.filter(billing_period=period).count(), 2
        )
        self.assertEqual(second.status, PaymentAttempt.Status.PENDING)

    def test_an_unknown_status_attempt_also_blocks_a_second_non_terminal_attempt(self):
        environment = make_environment()
        period = make_billing_period(make_subscription(environment))
        self._attempt(environment, period.subscription, period, PaymentAttempt.Status.UNKNOWN, "order-5")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._attempt(environment, period.subscription, period, PaymentAttempt.Status.PENDING, "order-6")

    def test_duplicate_merchant_order_id_is_rejected(self):
        environment = make_environment()
        subscription = make_subscription(environment)
        self._attempt(environment, subscription, None, PaymentAttempt.Status.SUCCEEDED, "dup-order")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._attempt(environment, subscription, None, PaymentAttempt.Status.INITIATED, "dup-order")

    def test_duplicate_provider_transaction_id_is_rejected(self):
        environment = make_environment()
        subscription = make_subscription(environment)
        self._attempt(
            environment, subscription, None, PaymentAttempt.Status.SUCCEEDED, "order-7",
            provider_transaction_id="txn-dup",
        )

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._attempt(
                    environment, subscription, None, PaymentAttempt.Status.SUCCEEDED, "order-8",
                    provider_transaction_id="txn-dup",
                )

    def test_two_null_provider_transaction_ids_are_both_allowed(self):
        """NULL != NULL in SQL uniqueness — only non-null duplicates are
        rejected; two attempts with no provider transaction id yet
        (e.g. both still `initiated`, before Kashier assigns one) must not
        collide with each other."""
        environment = make_environment()
        subscription = make_subscription(environment)
        self._attempt(environment, subscription, None, PaymentAttempt.Status.FAILED, "order-9")
        self._attempt(environment, subscription, None, PaymentAttempt.Status.FAILED, "order-10")
        self.assertEqual(PaymentAttempt.objects.filter(provider_transaction_id__isnull=True).count(), 2)


class ProviderEventDedupTests(TestCase):
    """AC-BILL-008-3."""

    def _event(self, dedup_key, **extra):
        return ProviderEvent.objects.create(
            dedup_key=dedup_key, mode=ProviderEvent.Mode.TEST, event_type="order.paid",
            signature_valid=True, **extra,
        )

    def test_two_events_with_same_dedup_key_raise_integrity_error(self):
        self._event("txn-1:SUCCESS:order.paid")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._event("txn-1:SUCCESS:order.paid")

    def test_events_with_different_dedup_keys_both_succeed(self):
        self._event("txn-1:SUCCESS:order.paid")
        self._event("txn-2:SUCCESS:order.paid")
        self.assertEqual(ProviderEvent.objects.count(), 2)


class NoCardDataFieldsTests(TestCase):
    """AC-BILL-008-6: no billing model may have a field capable of holding a
    PAN or CVV; the recurring-agreement reference stores opaque strings
    only."""

    FORBIDDEN_FIELD_NAME_FRAGMENTS = ("card_number", "pan", "cvv", "cvc", "security_code", "cardnumber")

    def test_no_model_field_name_looks_card_like(self):
        from django.apps import apps as django_apps

        offending = []
        for model in django_apps.get_app_config("billing").get_models():
            for field in model._meta.get_fields():
                field_name = field.name.lower()
                for fragment in self.FORBIDDEN_FIELD_NAME_FRAGMENTS:
                    if fragment in field_name:
                        offending.append(f"{model.__name__}.{field.name}")
        self.assertEqual(offending, [], f"card-like field name(s) found: {offending}")

    def test_recurring_agreement_only_stores_opaque_strings(self):
        environment = make_environment()
        subscription = make_subscription(environment)
        agreement = RecurringAgreement.objects.create(
            environment=environment, subscription=subscription,
            card_token="opaque-token-not-a-pan", kashier_agreement_id="agr_123",
            mode=RecurringAgreement.Mode.TEST,
        )
        # The token field accepts an arbitrary opaque string; nothing in the
        # schema distinguishes or privileges a PAN-shaped value, and no
        # separate "card number" field exists for one to be put in by
        # mistake (covered by the field-name scan above).
        self.assertEqual(agreement.card_token, "opaque-token-not-a-pan")


class NoForbiddenImportsTests(TestCase):
    """AC-BILL-008-7: `billing/` never imports `financials` or
    `config.months`. A static AST check so this is enforced even for
    code that isn't exercised by any other test."""

    def test_billing_module_files_do_not_import_financials_or_config_months(self):
        billing_dir = os.path.dirname(__file__)
        offending = []
        for root, _dirs, files in os.walk(billing_dir):
            if os.sep + "migrations" in root + os.sep:
                continue
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(root, filename)
                with open(path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=path)
                for node in ast.walk(tree):
                    modules = []
                    if isinstance(node, ast.Import):
                        modules = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        modules = [node.module]
                    for module in modules:
                        if module == "financials" or module.startswith("financials.") \
                                or module == "config.months":
                            offending.append(f"{path}: imports {module!r}")
        self.assertEqual(offending, [], f"forbidden import(s) found: {offending}")


class CascadeChoiceTests(TestCase):
    """Documents and locks in the deliberate cascade-vs-protect choice
    (module docstring): deleting an Environment must not silently destroy
    a PaymentAttempt."""

    def test_deleting_an_environment_with_a_payment_attempt_is_protected(self):
        from django.db.models.deletion import ProtectedError

        environment = make_environment()
        subscription = make_subscription(environment)
        PaymentAttempt.objects.create(
            environment=environment, subscription=subscription, billing_period=None,
            status=PaymentAttempt.Status.SUCCEEDED, merchant_order_id="protect-check",
            amount_minor_units=100000,
        )
        with self.assertRaises(ProtectedError):
            environment.delete()
