"""
Plans are now monthly / term / yearly instead of three student-cap tiers (plan_1/2/3). Every plan grants every
feature with no student cap; they differ only in the length of one paid period and in the price.

    monthly   1,850 EGP   30 days
    term      4,500 EGP   180 days
    yearly   10,000 EGP   365 days

This migration REFUSES to run if any subscription or payment attempt still points at an old plan: mapping a
paying customer from "plan_2" to some new plan is a commercial decision, not something to guess in a migration.
Empty such tables (or move those rows by hand), then migrate again. The list below is a frozen copy of
`billing/catalog.py` (migrations must not import live code); `billing/test_catalog.py` keeps the two equal.
"""
from django.db import migrations, models

OLD_KEYS = ["plan_1", "plan_2", "plan_3"]
OLD_PLANS = [
    {"key": "plan_1", "name": "Plan 1", "price_minor_units": 100000, "max_students": 400, "period_days": 30},
    {"key": "plan_2", "name": "Plan 2", "price_minor_units": 150000, "max_students": 800, "period_days": 30},
    {"key": "plan_3", "name": "Plan 3", "price_minor_units": 200000, "max_students": None, "period_days": 30},
]
NEW_PLANS = [
    {"key": "monthly", "name": "شهري", "price_minor_units": 185000, "period_days": 30},
    {"key": "term", "name": "كل ترم", "price_minor_units": 450000, "period_days": 180},
    {"key": "yearly", "name": "سنوي", "price_minor_units": 1000000, "period_days": 365},
]


def _write(apps, plans, remove_keys):
    Plan = apps.get_model("billing", "Plan")
    Subscription = apps.get_model("billing", "Subscription")
    PaymentAttempt = apps.get_model("billing", "PaymentAttempt")
    stale = Plan.objects.filter(key__in=remove_keys)
    if Subscription.objects.filter(plan__in=stale).exists() or PaymentAttempt.objects.filter(plan__in=stale).exists():
        raise RuntimeError(
            "billing.0005: a subscription or payment attempt still uses one of the plans being replaced "
            f"({', '.join(remove_keys)}). Move or remove those rows first; this migration will not guess."
        )
    stale.delete()
    for data in plans:
        Plan.objects.update_or_create(
            key=data["key"],
            defaults={
                "name": data["name"], "price_minor_units": data["price_minor_units"], "currency": "EGP",
                "max_students": data.get("max_students"), "period_days": data["period_days"], "is_active": True,
            },
        )


def to_duration_plans(apps, schema_editor):
    _write(apps, NEW_PLANS, OLD_KEYS)


def to_tier_plans(apps, schema_editor):
    _write(apps, OLD_PLANS, [p["key"] for p in NEW_PLANS])


class Migration(migrations.Migration):

    dependencies = [
        ("billing", "0004_attempt_plan_and_event_agreement"),
    ]

    operations = [
        migrations.AddField(
            model_name="plan",
            name="period_days",
            field=models.PositiveSmallIntegerField(default=30),
        ),
        migrations.AlterField(
            model_name="plan",
            name="key",
            field=models.CharField(
                choices=[("monthly", "Monthly"), ("term", "Term"), ("yearly", "Yearly")], max_length=20, unique=True
            ),
        ),
        migrations.RunPython(to_duration_plans, to_tier_plans),
    ]
