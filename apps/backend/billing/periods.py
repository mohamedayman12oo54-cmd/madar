"""
BILL-WU-024 — billing-period computation (30 elapsed days, server-
authoritative). A billing period is exactly 30 elapsed days, never a
calendar month (commercial-model §Billing period) — all arithmetic here
is on aware UTC instants via `timedelta`, which is immune to a DST-
induced 23 h or 25 h "day" in any display timezone. `Africa/Cairo`
(`settings.py`'s `TIME_ZONE`) is used only for display elsewhere; this
module never imports `config.months` (that module is calendar-month
arithmetic for the unrelated Student-to-Teacher fee, DAT-5/BND-1) and
never performs calendar-month arithmetic of its own.
"""
from django.utils import timezone

PERIOD_LENGTH = timezone.timedelta(days=30)


def next_period(start):
    """`(start, start + 30 elapsed days)`. `start` must be an aware
    datetime; the return value never depends on any calendar or
    timezone — only elapsed time."""
    return start, start + PERIOD_LENGTH


def current_period(subscription, now=None):
    """The subscription's most recently started `BillingPeriod` as of
    `now` (the latest period whose `period_start <= now`), or `None` if
    none exists yet. Deliberately not required to still *contain* `now`:
    a period remains "the current one" to reason about even in the
    instant it has just elapsed, until the next period is created."""
    now = now or timezone.now()
    return subscription.periods.filter(period_start__lte=now).order_by("-period_start").first()


def renewal_due(subscription, now=None, lead=None):
    """True when the current period ends at or before `now + lead`.
    `lead` is an operational knob (default zero) a caller may set to
    start a renewal attempt some time before the period's exact end;
    this module does not read it from settings — callers decide."""
    now = now or timezone.now()
    lead = lead if lead is not None else timezone.timedelta(0)
    period = current_period(subscription, now)
    if period is None:
        return False
    return period.period_end <= now + lead
