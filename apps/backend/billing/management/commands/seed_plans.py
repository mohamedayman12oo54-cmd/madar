"""Writes the three real plans (billing/catalog.py) into the database: monthly 1,850 / term 4,500 / yearly 10,000 EGP.
Idempotent and exact — it only ever creates or corrects those three rows. Needed after `manage.py flush`, which
empties the plan table the migration filled. Prints what it did; changes nothing else."""
from django.core.management.base import BaseCommand
from django.db import transaction

from billing.catalog import CURRENCY, PLAN_CATALOG
from billing.models import Plan


class Command(BaseCommand):
    help = "Create or correct the monthly / term / yearly plans."

    @transaction.atomic
    def handle(self, *args, **options):
        for data in PLAN_CATALOG:
            plan, created = Plan.objects.update_or_create(
                key=data["key"],
                defaults={
                    "name": data["name"], "price_minor_units": data["price_minor_units"], "currency": CURRENCY,
                    "max_students": None, "period_days": data["period_days"], "is_active": True,
                },
            )
            self.stdout.write(
                f"{'created' if created else 'ok     '} {plan.key:<8} {plan.price_minor_units / 100:>9,.2f} {plan.currency}"
                f"  every {plan.period_days} days"
            )
