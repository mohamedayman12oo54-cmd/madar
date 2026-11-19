"""Small shared helpers for the control endpoints: date ranges, pagination, time series, CSV, error shapes."""
import csv
import io
import re
from datetime import date, datetime, time, timedelta

from django.db.models import Count
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import serializers
from rest_framework.views import APIView

from .access import HasControlPerm

PRESETS = {"today": 1, "7d": 7, "30d": 30, "90d": 90}
MAX_CUSTOM_DAYS = 400


class ControlView(APIView):
    """Base for control endpoints: `perm = "users.view"` (or a tuple = any of) is checked on every request."""

    perm = ()

    def get_permissions(self):
        keys = (self.perm,) if isinstance(self.perm, str) else tuple(self.perm)
        return [HasControlPerm.require(*keys)()]


_ID = re.compile(r"[0-9]{1,9}")  # ASCII digits only, always inside a 32-bit column: no overflow reaches the database


def as_id(value):
    """`"42"` -> 42; anything else (huge, negative, non-ASCII digits like "²", junk) -> None."""
    return int(value) if isinstance(value, str) and _ID.fullmatch(value) else None


def id_param(request, name):
    """A numeric id from the query string: None when absent, a 400 (not a database error) when present but invalid."""
    raw = request.query_params.get(name, "")
    if raw == "":
        return None
    v = as_id(raw)
    if v is None:
        raise invalid(**{name: "قيمة رقمية غير صالحة."})
    return v


def date_param(request, name):
    """A calendar date (YYYY-MM-DD) from the query string: None when absent, a 400 when malformed. The ORM would raise
    a ValidationError (an HTTP 500) on `?from=not-a-date`."""
    raw = request.query_params.get(name, "")
    if raw == "":
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        raise invalid(**{name: "تاريخ غير صالح. الصيغة المطلوبة YYYY-MM-DD."})


def invalid(**fields):
    """A 400 in the shape config.exceptions produces for serializer errors."""
    return serializers.ValidationError({k: [v] for k, v in fields.items()})


def parse_range(request, default="30d"):
    """-> (start, end, previous_start, label). `start`/`end` are aware datetimes, end exclusive. The previous
    period is the same length directly before `start` (used for the trend arrows)."""
    q = request.query_params
    now = timezone.now()
    tz = timezone.get_current_timezone()
    preset = q.get("range") or default
    if preset == "custom":
        try:
            d1 = date.fromisoformat(q.get("from", ""))
            d2 = date.fromisoformat(q.get("to", ""))
        except ValueError:
            raise invalid(range="حدّد تاريخ بداية ونهاية صحيحين.")
        if d2 < d1 or (d2 - d1).days > MAX_CUSTOM_DAYS:
            raise invalid(range=f"المدى يجب ألا يتجاوز {MAX_CUSTOM_DAYS} يومًا، والنهاية بعد البداية.")
        start = timezone.make_aware(datetime.combine(d1, time.min), tz)
        end = timezone.make_aware(datetime.combine(d2 + timedelta(days=1), time.min), tz)
    elif preset in PRESETS:
        days = PRESETS[preset]
        today = timezone.localtime(now).date()
        start = timezone.make_aware(datetime.combine(today - timedelta(days=days - 1), time.min), tz)
        end = timezone.make_aware(datetime.combine(today + timedelta(days=1), time.min), tz)
    else:
        raise invalid(range="مدى غير معروف.")
    return start, end, start - (end - start), preset


def day_list(start, end):
    d = timezone.localtime(start).date()
    last = timezone.localtime(end - timedelta(seconds=1)).date()
    out = []
    while d <= last:
        out.append(d)
        d += timedelta(days=1)
    return out


def series(qs, field, start, end, **count_kwargs):
    """Zero-filled per-day counts of `qs` rows whose `field` falls in [start, end)."""
    rows = (qs.filter(**{f"{field}__gte": start, f"{field}__lt": end})
            .annotate(_d=TruncDate(field)).values("_d").annotate(n=Count("id", **count_kwargs)).values_list("_d", "n"))
    by_day = dict(rows)
    return [{"date": d.isoformat(), "value": by_day.get(d, 0)} for d in day_list(start, end)]


def pct_change(current, previous):
    if not previous:
        return None if not current else 100.0
    return round((current - previous) * 100.0 / previous, 1)


def paginate(request, qs, build, default_size=20, max_size=100):
    q = request.query_params
    try:
        size = min(max(int(q.get("page_size", default_size)), 1), max_size)
        page = min(max(int(q.get("page", 1)), 1), 100_000)  # a huge OFFSET is a database error, not a page
    except ValueError:
        raise invalid(page="رقم الصفحة غير صالح.")
    total = qs.count()
    rows = list(qs[(page - 1) * size: page * size])
    return {"count": total, "page": page, "page_size": size, "pages": max((total + size - 1) // size, 1),
            "results": [build(r) for r in rows]}


def ordering(request, allowed, default):
    """`?sort=name` / `?sort=-created_at`, restricted to `allowed` (a dict public-name -> db expression)."""
    raw = request.query_params.get("sort") or default
    desc = raw.startswith("-")
    key = raw.lstrip("-")
    if key not in allowed:
        key, desc = default.lstrip("-"), default.startswith("-")
    field = allowed[key]
    return [f"-{field}" if desc else field, "-id"]


def clean_search(request, name="search"):
    return (request.query_params.get(name, "") or "").replace("\x00", "").strip()[:100]


def iso(dt):
    return dt.isoformat() if dt else None


def csv_response(filename, header, rows):
    """A UTF-8 (with BOM, so Excel reads Arabic) CSV download. Cells that start with a formula character are
    prefixed so a hostile value typed by a customer cannot execute when the team opens the file."""
    buf = io.StringIO()
    w = csv.writer(buf)

    def safe(v):
        v = "" if v is None else v
        if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r"):
            return "'" + v
        return v

    w.writerow(header)
    for r in rows:
        w.writerow([safe(c) for c in r])
    resp = HttpResponse("﻿" + buf.getvalue(), content_type="text/csv; charset=utf-8")
    resp["Content-Disposition"] = f'attachment; filename="{filename}"'
    resp["X-Content-Type-Options"] = "nosniff"
    return resp
