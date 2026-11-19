"""Execution records for the background commands. Wrap one run of a worker:

    with record_run("process_notifications") as run:
        r = deliver_pending(...)
        run.processed, run.failed = r["sent"] + r["failed"], r["failed"]

A raised exception is recorded as a failed run and re-raised; the record itself must never break the worker."""
import logging
import time
from contextlib import contextmanager

from django.utils import timezone

log = logging.getLogger(__name__)

# Commands the Control Center monitors: (Arabic label, how often a scheduled run is expected, in minutes). The
# interval is ONLY used to flag a worker that has gone quiet, and only meaningful when an operator runs it on a
# schedule — in "thread" mode notifications and AI operations are also delivered in-process.
MONITORED_JOBS = {
    "process_notifications": ("معالجة الإشعارات", 15),
    "process_ai_operations": ("معالجة عمليات الذكاء الاصطناعي", 15),
    "process_guardian_alerts": ("تنبيهات أولياء الأمور", 24 * 60 + 60),
    "purge_pending_auth": ("تنظيف جلسات التحقق المنتهية", 24 * 60 + 60),
    "process_platform_notices": ("إرسال إشعارات المنصة", 15),
}


class _Run:
    processed = 0
    failed = 0


@contextmanager
def record_run(name):
    run = _Run()
    started = timezone.now()
    t0 = time.monotonic()
    error = ""
    try:
        yield run
    except BaseException as exc:  # recorded, then re-raised untouched
        error = f"{type(exc).__name__}: {exc}"[:300]
        raise
    finally:
        try:
            from .models import JobRun

            JobRun.objects.create(
                name=name, status=JobRun.Status.FAILED if error else JobRun.Status.OK, started_at=started,
                finished_at=timezone.now(), duration_ms=int((time.monotonic() - t0) * 1000),
                processed=int(run.processed), failed_items=int(run.failed), error=error)
        except Exception:  # pragma: no cover - monitoring must never take a worker down
            log.exception("could not record job run %s", name)
