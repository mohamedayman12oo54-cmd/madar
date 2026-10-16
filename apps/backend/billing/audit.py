"""
BILL-WU-035 — billing observability: a structured `billing` logger
(`config/settings.py` LOGGING) and the immutable transition-history
record (ADR-014). This is the one place any billing module writes a
log line about money-state or a history row — nothing else in
`billing/*` calls `logging.getLogger` or creates a `BillingTransition`
directly, so both are redacted/shaped exactly once, here.

**Open item carried forward (this unit's own tracked open item,
NODE-Vendors):** no APM or error-tracking vendor exists; alerts are
log events plus the runbook's query/manual check, not a paging
integration. Selecting a vendor is this unit's own explicit exclusion.
"""
import logging

from .models import BillingTransition
from .redaction import redact_mapping

logger = logging.getLogger("billing")


def log(event, **fields):
    """One structured, redacted key=value line per call. `event` is a
    short machine-readable label (e.g. "webhook_verified",
    "attempt_charged", "renewal_run_summary"); `fields` are redacted
    before they are ever formatted into the message, so a caller can
    pass a raw-shaped dict without pre-sanitizing it itself."""
    safe_fields = redact_mapping(fields)
    rendered = " ".join(f"{k}={v!r}" for k, v in safe_fields.items())
    logger.info("event=%s %s", event, rendered)


def record_transition(
    *, model_name, object_id, field, to_value, environment=None, environment_id=None, from_value="", actor=""
):
    """AC-BILL-035-2: one append-only history row per Subscription/
    PaymentAttempt state change. Always a `.create()` — this model is
    never updated or deleted. Accepts either a resolved `environment`
    instance or a bare `environment_id` (a bulk `.update()` sweep that
    never fetched the instance can pass the id it already selected
    instead of re-querying one just to satisfy this call)."""
    create_kwargs = {"environment_id": environment_id} if environment is None else {"environment": environment}
    BillingTransition.objects.create(
        model_name=model_name, object_id=object_id,
        field=field, from_value=from_value or "", to_value=to_value, actor=actor,
        **create_kwargs,
    )
