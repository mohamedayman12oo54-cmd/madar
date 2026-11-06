"""The real plans: monthly 1,850 / term 4,500 / yearly 10,000 EGP, one feature set, no student cap — and nothing
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
            "monthly": (185000, 30, "EGP"),    # 1,850 EGP every 30 days
            "term": (450000, 180, "EGP"),      # 4,500 EGP every 180 days (one term)
            "yearly": (1000000, 365, "EGP"),   # 10,000 EGP every 365 days
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

    def test_the_catalog_and_the_migrations_frozen_copy_agree(self):
        migration = importlib.import_module("billing.migrations.0005_plans_by_duration")
        self.assertEqual(
            sorted(migration.NEW_PLANS, key=lambda p: p["key"]),
            sorted(({k: v for k, v in p.items()} for p in PLAN_CATALOG), key=lambda p: p["key"]))
        self.assertEqual(CURRENCY, "EGP")

    def test_seed_plans_repairs_a_flushed_or_tampered_catalog_and_adds_nothing_else(self):
        Plan.objects.all().delete()
        out = StringIO()
        call_command("seed_plans", stdout=out)
        call_command("seed_plans", stdout=out)  # idempotent
        self.assertEqual(Plan.objects.count(), 3)
        Plan.objects.filter(key="term").update(price_minor_units=1)
        call_command("seed_plans", stdout=out)
        self.assertEqual(Plan.objects.get(key="term").price_minor_units, 450000)
