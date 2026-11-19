"""The real plans: monthly 1,500 / term 5,000 / yearly 9,500 EGP, one feature set, no student cap — and nothing
else in the catalog."""
import importlib
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from . import capabilities
from .catalog import CURRENCY, PLAN_CATALOG
from .entitlements import TRIAL_DAYS
from .models import Plan


class CatalogTests(TestCase):
    def test_the_prices_and_period_lengths_are_exactly_the_agreed_ones(self):
        got = {p.key: (p.price_minor_units, p.period_days, p.currency) for p in Plan.objects.all()}
        self.assertEqual(got, {
            "monthly": (150000, 30, "EGP"),    # 1,500 EGP every 30 days
            "term": (500000, 180, "EGP"),      # 5,000 EGP every 180 days (one term)
            "yearly": (950000, 365, "EGP"),   # 9,500 EGP every 365 days
        })

    def test_there_are_exactly_three_plans_and_no_others(self):
        self.assertEqual(Plan.objects.count(), 3)
        self.assertFalse(Plan.objects.filter(key__startswith="plan_").exists())

    def test_no_plan_has_a_student_cap_and_all_are_active(self):
        self.assertEqual(set(Plan.objects.values_list("max_students", flat=True)), {None})
        self.assertTrue(all(Plan.objects.values_list("is_active", flat=True)))

    def test_every_plan_grants_every_feature_and_so_does_the_trial(self):
        for key in ("monthly", "term", "yearly"):
            self.assertEqual(capabilities.capabilities_for_plan(key), capabilities.ALL_CAPABILITIES, key)
        self.assertEqual(capabilities.TRIAL_CAPABILITIES, capabilities.ALL_CAPABILITIES)

    def test_the_free_trial_is_sixteen_days(self):
        self.assertEqual(TRIAL_DAYS, 16)

    def test_the_catalog_and_the_migrations_frozen_copies_agree(self):
        # 0005 froze the plan shape (key / name / period); 0006 froze the current prices.
        shape = importlib.import_module("billing.migrations.0005_plans_by_duration")
        prices = importlib.import_module("billing.migrations.0006_new_plan_prices")
        self.assertEqual(
            sorted(({k: p[k] for k in ("key", "name", "period_days")} for p in shape.NEW_PLANS), key=lambda p: p["key"]),
            sorted(({k: p[k] for k in ("key", "name", "period_days")} for p in PLAN_CATALOG), key=lambda p: p["key"]))
        self.assertEqual(prices.NEW, {p["key"]: p["price_minor_units"] for p in PLAN_CATALOG})
        self.assertEqual(CURRENCY, "EGP")

    def test_new_list_prices(self):
        self.assertEqual({p["key"]: p["price_minor_units"] // 100 for p in PLAN_CATALOG},
                         {"monthly": 1500, "term": 5000, "yearly": 9500})

    def test_seed_plans_repairs_a_flushed_or_tampered_catalog_and_adds_nothing_else(self):
        Plan.objects.all().delete()
        out = StringIO()
        call_command("seed_plans", stdout=out)
        call_command("seed_plans", stdout=out)  # idempotent
        self.assertEqual(Plan.objects.count(), 3)
        Plan.objects.filter(key="term").update(price_minor_units=1)
        call_command("seed_plans", stdout=out)
        self.assertEqual(Plan.objects.get(key="term").price_minor_units, 500000)


class PriceChangePreservesHistoryTests(TestCase):
    def test_repricing_changes_only_the_plan_rows_not_past_charges(self):
        from django.apps import apps

        from billing.models import PaymentAttempt, Subscription
        from billing.tests import make_environment  # same helper the other billing tests use

        migration = importlib.import_module("billing.migrations.0006_new_plan_prices")
        env = make_environment("repricing")
        sub = Subscription.objects.create(environment=env)
        plan = Plan.objects.get(key="monthly")
        Plan.objects.filter(pk=plan.pk).update(price_minor_units=185000)  # the old list price
        attempt = PaymentAttempt.objects.create(environment=env, subscription=sub, plan=plan, merchant_order_id="old-1",
                                                amount_minor_units=185000)
        migration._set(migration.NEW)(apps, None)
        attempt.refresh_from_db()
        self.assertEqual(attempt.amount_minor_units, 185000)               # what was charged stays
        self.assertEqual(Plan.objects.get(key="monthly").price_minor_units, 150000)  # what is charged next changes
