"""
BILL-WU-009 — seed the three decided plans.

Numbers come only from `docs/01-product/commercial-model.md` §Plans at the
time this migration was written: EGP 1,000/1,500/2,000 per 30-elapsed-day
cycle, student caps 400/800/none. Idempotent (keyed by `Plan.key`): running
this migration again (or on a DB that was partially seeded by hand) updates
the existing rows to match rather than creating duplicates, since `Plan.key`
is unique.
"""
from django.db import migrations

PLANS = [
    {"key": "plan_1", "name": "Plan 1", "price_minor_units": 100000, "max_students": 400},
    {"key": "plan_2", "name": "Plan 2", "price_minor_units": 150000, "max_students": 800},
    {"key": "plan_3", "name": "Plan 3", "price_minor_units": 200000, "max_students": None},
]


def seed_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    for data in PLANS:
        Plan.objects.update_or_create(
            key=data["key"],
            defaults={
                "name": data["name"],
                "price_minor_units": data["price_minor_units"],
                "currency": "EGP",
                "max_students": data["max_students"],
                "is_active": True,
            },
        )


def unseed_plans(apps, schema_editor):
    Plan = apps.get_model("billing", "Plan")
    Plan.objects.filter(key__in=[data["key"] for data in PLANS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_plans, unseed_plans),
    ]
