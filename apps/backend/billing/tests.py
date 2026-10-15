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


class PlanSeedDataTests(TestCase):
    """BILL-WU-009 — AC-BILL-009-1. The migration under test
    (0002_seed_plans) already ran when Django built the test database, so
    this only needs to read back what it produced and pin it against the
    exact numbers in commercial-model.md §Plans — not re-run the
    migration."""

    def test_exactly_three_plans_exist_with_the_decided_numbers(self):
        self.assertEqual(Plan.objects.count(), 3)

        plan_1 = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.assertEqual(plan_1.price_minor_units, 100000)  # EGP 1,000
        self.assertEqual(plan_1.currency, "EGP")
        self.assertEqual(plan_1.max_students, 400)

        plan_2 = Plan.objects.get(key=Plan.Key.PLAN_2)
        self.assertEqual(plan_2.price_minor_units, 150000)  # EGP 1,500
        self.assertEqual(plan_2.max_students, 800)

        plan_3 = Plan.objects.get(key=Plan.Key.PLAN_3)
        self.assertEqual(plan_3.price_minor_units, 200000)  # EGP 2,000
        self.assertIsNone(plan_3.max_students)  # no plan-level numerical cap

    def test_all_three_plans_are_active(self):
        self.assertEqual(Plan.objects.filter(is_active=True).count(), 3)

    def test_the_billing_period_is_the_same_30_days_for_every_plan(self):
        """There is no per-Plan period field (by design — see
        capabilities.py) because commercial-model.md §Plans gives every
        plan the identical '30 elapsed days' period; this asserts that
        single shared constant rather than a Plan-model field."""
        from .capabilities import BILLING_PERIOD_DAYS

        self.assertEqual(BILLING_PERIOD_DAYS, 30)

    def test_rerunning_seed_plans_updates_rather_than_duplicates(self):
        """Calling the migration's own seed function again (as if the
        migration ran twice, or a DB was hand-seeded first) must update the
        existing three rows in place, never create duplicates — `Plan.key`
        is unique, and the function uses `update_or_create` keyed by it."""
        import importlib

        seed_module = importlib.import_module("billing.migrations.0002_seed_plans")
        seed_module.seed_plans(apps=_RealAppsShim(), schema_editor=None)
        self.assertEqual(Plan.objects.count(), 3)


class _RealAppsShim:
    """`seed_plans(apps, schema_editor)` expects a migration-style `apps`
    registry (`apps.get_model(app_label, name)`); the real app registry
    satisfies that same interface, so re-use it rather than reimplementing
    a fake just to call the function a second time from a test."""

    @staticmethod
    def get_model(app_label, name):
        from django.apps import apps as django_apps

        return django_apps.get_model(app_label, name)


class CapabilityRegistryTests(TestCase):
    """BILL-WU-009 — AC-BILL-009-2: the registry maps each plan and the
    trial to exactly the feature sets commercial-model.md describes."""

    def test_plan_1_has_only_quiz_from_video(self):
        from .capabilities import AI_QUIZ_FROM_VIDEO, PLAN_CAPABILITIES
        from .models import Plan as PlanModel

        self.assertEqual(PLAN_CAPABILITIES[PlanModel.Key.PLAN_1], frozenset({AI_QUIZ_FROM_VIDEO}))

    def test_plan_2_is_plan_1_plus_video_content_chat(self):
        from .capabilities import AI_QUIZ_FROM_VIDEO, AI_VIDEO_CONTENT_CHAT, PLAN_CAPABILITIES
        from .models import Plan as PlanModel

        self.assertEqual(
            PLAN_CAPABILITIES[PlanModel.Key.PLAN_2],
            frozenset({AI_QUIZ_FROM_VIDEO, AI_VIDEO_CONTENT_CHAT}),
        )

    def test_plan_3_is_plan_2_plus_performance_analysis(self):
        from .capabilities import (
            AI_PERFORMANCE_ANALYSIS, AI_QUIZ_FROM_VIDEO, AI_VIDEO_CONTENT_CHAT, PLAN_CAPABILITIES,
        )
        from .models import Plan as PlanModel

        self.assertEqual(
            PLAN_CAPABILITIES[PlanModel.Key.PLAN_3],
            frozenset({AI_QUIZ_FROM_VIDEO, AI_VIDEO_CONTENT_CHAT, AI_PERFORMANCE_ANALYSIS}),
        )

    def test_trial_equals_plan_3_feature_set_with_its_own_250_cap(self):
        from .capabilities import PLAN_CAPABILITIES, TRIAL_CAPABILITIES, TRIAL_STUDENT_CAP
        from .models import Plan as PlanModel

        self.assertEqual(TRIAL_CAPABILITIES, PLAN_CAPABILITIES[PlanModel.Key.PLAN_3])
        self.assertEqual(TRIAL_STUDENT_CAP, 250)
        # The trial cap is independent of (and smaller than) every plan cap,
        # including Plan 3's absence of a plan-level cap.
        plan_1 = Plan.objects.get(key=PlanModel.Key.PLAN_1)
        plan_2 = Plan.objects.get(key=PlanModel.Key.PLAN_2)
        self.assertLess(TRIAL_STUDENT_CAP, plan_1.max_students)
        self.assertLess(TRIAL_STUDENT_CAP, plan_2.max_students)

    def test_capabilities_for_plan_helper_matches_the_table(self):
        from .capabilities import PLAN_CAPABILITIES, capabilities_for_plan
        from .models import Plan as PlanModel

        for key in (PlanModel.Key.PLAN_1, PlanModel.Key.PLAN_2, PlanModel.Key.PLAN_3):
            self.assertEqual(capabilities_for_plan(key), PLAN_CAPABILITIES[key])

    def test_capabilities_for_plan_rejects_an_unknown_key(self):
        from .capabilities import capabilities_for_plan

        with self.assertRaises(KeyError):
            capabilities_for_plan("not_a_real_plan")
