"""New list prices: monthly 1,500 / term 5,000 / yearly 9,500 EGP (was 1,850 / 4,500 / 10,000).

Only the three `Plan` rows change. History is untouched on purpose: every `PaymentAttempt` and `AmountOwed` copied its
amount from the plan when it was created, so past transactions keep the price that was actually charged. An existing
subscription keeps its current paid period; its NEXT renewal is priced from the plan row, i.e. at the new price.
The list below is a frozen copy of `billing/catalog.py` (migrations must not import live code);
`billing/test_catalog.py` keeps the two equal.
"""
from django.db import migrations

NEW = {"monthly": 150000, "term": 500000, "yearly": 950000}
OLD = {"monthly": 185000, "term": 450000, "yearly": 1000000}


def _set(prices):
    def run(apps, schema_editor):
        Plan = apps.get_model("billing", "Plan")
        for key, minor in prices.items():
            Plan.objects.filter(key=key).update(price_minor_units=minor)

    return run


class Migration(migrations.Migration):
    dependencies = [("billing", "0005_plans_by_duration")]
    operations = [migrations.RunPython(_set(NEW), _set(OLD))]
