"""Calendar-month helpers shared by Payment / Rating / State (all keyed by
Enrollment x Calendar Month — docs: glossary). A month is stored as the FIRST
day of that month so (enrollment, month) is a clean unique key."""
import datetime as dt
import re

from django.utils import timezone
from rest_framework import serializers

_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
MAX_MONTHS_AHEAD = 1
MAX_MONTHS_BACK = 36


def parse_month(value) -> dt.date:
    """'2026-09' -> date(2026, 9, 1); anything else is a validation error."""
    m = _RE.match(str(value or "").strip())
    if not m:
        raise serializers.ValidationError("الشهر يجب أن يكون بصيغة YYYY-MM.")
    first = dt.date(int(m.group(1)), int(m.group(2)), 1)
    today = timezone.localdate().replace(day=1)
    index = lambda d: d.year * 12 + d.month  # noqa: E731
    if index(first) - index(today) > MAX_MONTHS_AHEAD or index(today) - index(first) > MAX_MONTHS_BACK:
        raise serializers.ValidationError("الشهر خارج النطاق المسموح.")
    return first


def current_month() -> dt.date:
    return timezone.localdate().replace(day=1)


def month_bounds(first: dt.date):
    nxt = (first.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return first, nxt
