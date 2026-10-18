"""
BILL-WU-024 — billing-period arithmetic tests.
"""
import datetime as dt
import os
import zoneinfo

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from environments.tenancy_testing import TenantTestCase

from .models import BillingPeriod, Plan, Subscription
from .periods import current_period, next_period, renewal_due

CAIRO = zoneinfo.ZoneInfo("Africa/Cairo")


def _cairo(y, m, d, h=12):
    return dt.datetime(y, m, d, h, tzinfo=CAIRO)


class NextPeriodArithmeticTests(SimpleTestCase):
    """AC-BILL-024-1."""

    def test_end_minus_start_is_exactly_2592000_seconds_in_february(self):
        start = _cairo(2026, 2, 10)
        start, end = next_period(start)
        self.assertEqual((end - start).total_seconds(), 2_592_000)

    def test_end_minus_start_is_exactly_2592000_seconds_in_march(self):
        start = _cairo(2026, 3, 5)
        start, end = next_period(start)
        self.assertEqual((end - start).total_seconds(), 2_592_000)

    def test_end_minus_start_is_exact_across_a_cairo_spring_forward_week(self):
        # Africa/Cairo moves 2:00 -> 3:00 on 2023-04-28 in this tzdata.
        start = _cairo(2023, 4, 20)
        start, end = next_period(start)
        self.assertEqual((end - start).total_seconds(), 2_592_000)
        self.assertEqual(end, start + dt.timedelta(days=30))

    def test_end_minus_start_is_exact_across_a_cairo_fall_back_week(self):
        # Africa/Cairo moves 3:00 -> 2:00 on 2023-10-27 in this tzdata.
        start = _cairo(2023, 10, 20)
        start, end = next_period(start)
        self.assertEqual((end - start).total_seconds(), 2_592_000)
        self.assertEqual(end, start + dt.timedelta(days=30))


class PeriodChainTests(SimpleTestCase):
    """AC-BILL-024-2."""

    def test_a_chain_of_13_periods_ends_390_days_after_the_first_start(self):
        start = _cairo(2026, 1, 1)
        first_start = start
        for _ in range(13):
            start, end = next_period(start)
            start = end
        self.assertEqual(start, first_start + dt.timedelta(days=390))


class NoCalendarMonthImportTests(SimpleTestCase):
    """AC-BILL-024-3: `billing/` contains no import of `config.months`."""

    def test_billing_never_imports_config_months(self):
        import ast

        billing_dir = os.path.dirname(__file__)
        offending = []
        for root, dirs, files in os.walk(billing_dir):
            dirs[:] = [d for d in dirs if d != "migrations"]
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
                        if module == "config.months" or module.startswith("config.months."):
                            offending.append(f"{path}: imports {module!r}")
                        if module == "config" and any(a.name == "months" for a in node.names):
                            offending.append(f"{path}: imports {module!r}.months")
        self.assertEqual(offending, [], f"forbidden config.months import(s): {offending}")


def _make_subscription(environment, **extra):
    return Subscription.objects.create(environment=environment, **extra)


class RenewalDueBoundaryTests(TenantTestCase):
    """AC-BILL-024-4."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.subscription = _make_subscription(self.env_a, plan=self.plan)
        self.start = timezone.now() - timezone.timedelta(days=10)
        self.period = BillingPeriod.objects.create(
            environment=self.env_a, subscription=self.subscription,
            period_start=self.start, period_end=self.start + timezone.timedelta(days=30),
        )

    def test_renewal_due_is_false_one_microsecond_before_the_end(self):
        now = self.period.period_end - timezone.timedelta(microseconds=1)
        self.assertFalse(renewal_due(self.subscription, now))

    def test_renewal_due_is_true_exactly_at_the_end(self):
        now = self.period.period_end
        self.assertTrue(renewal_due(self.subscription, now))

    def test_renewal_due_respects_a_nonzero_lead(self):
        lead = timezone.timedelta(days=2)
        just_before_window = self.period.period_end - lead - timezone.timedelta(microseconds=1)
        at_window_start = self.period.period_end - lead
        self.assertFalse(renewal_due(self.subscription, just_before_window, lead=lead))
        self.assertTrue(renewal_due(self.subscription, at_window_start, lead=lead))

    def test_renewal_due_is_false_with_no_periods_at_all(self):
        other_sub = _make_subscription(self.env_b, plan=self.plan)
        self.assertFalse(renewal_due(other_sub, timezone.now()))


class CurrentPeriodLookupTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.subscription = _make_subscription(self.env_a, plan=self.plan)

    def test_current_period_finds_the_latest_started_period(self):
        now = timezone.now()
        older_start = now - timezone.timedelta(days=60)
        older = BillingPeriod.objects.create(
            environment=self.env_a, subscription=self.subscription,
            period_start=older_start, period_end=older_start + timezone.timedelta(days=30),
        )
        newer_start = now - timezone.timedelta(days=10)
        newer = BillingPeriod.objects.create(
            environment=self.env_a, subscription=self.subscription,
            period_start=newer_start, period_end=newer_start + timezone.timedelta(days=30),
        )
        self.assertEqual(current_period(self.subscription, now).pk, newer.pk)

    def test_current_period_is_none_when_none_exist(self):
        self.assertIsNone(current_period(self.subscription, timezone.now()))
