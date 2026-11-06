"""
The subscription plans: ONE feature set, three ways to pay for it. Every plan grants every feature with no student
cap; they differ only in how long one paid period lasts and what it costs. Prices are Egyptian pounds, stored as
piastres (integer minor units — see `Plan.price_minor_units`).

    monthly   1,850 EGP   every 30 days
    term      4,500 EGP   every 180 days (one school term)
    yearly   10,000 EGP   every 365 days

This is the single definition. The data migration `0005_plans_by_duration` carries its own frozen copy (migrations
must not import live code) and `test_catalog.py` fails if the two ever differ. `manage.py seed_plans` writes this
catalog into an empty or flushed database; it never invents anything else.
"""

PLAN_CATALOG = (
    {"key": "monthly", "name": "شهري", "price_minor_units": 185000, "period_days": 30},
    {"key": "term", "name": "كل ترم", "price_minor_units": 450000, "period_days": 180},
    {"key": "yearly", "name": "سنوي", "price_minor_units": 1000000, "period_days": 365},
)
CURRENCY = "EGP"
