"""
Starts delivering notifications the moment they are saved, inside this process, instead of waiting for someone to
run `process_notifications`. Before this, nothing sent a push unless that command happened to be running as a
separate process — with none running, every notification stayed `pending` forever.

Same shape as `ai.dispatch`:
* started with `transaction.on_commit`: a request that rolls back never starts work for rows that do not exist;
* ONE drain thread per process at a time (a burst of notifications is one pass, not hundreds of threads); it keeps
  draining until nothing is pending;
* delivery itself goes through `notifications.delivery.deliver_pending`, which claims rows so nothing is sent
  twice however many threads, processes or `process_notifications` workers race for it;
* a row whose dispatch was lost (process restarted mid-pass) is picked up by the next notification's pass, or by
  `process_notifications`.

`NOTIFICATION_WORKER_MODE=external` turns it off and leaves everything to the command (cron / `--loop`).
"""
import logging
import threading

from django.conf import settings
from django.db import connections, transaction

log = logging.getLogger(__name__)

_lock = threading.Lock()
_running = False
_rerun = False


def enabled() -> bool:
    return getattr(settings, "NOTIFICATION_WORKER_MODE", "external") == "thread"


def kick() -> None:
    """Call right after creating notifications (inside the same transaction). No-op in `external` mode."""
    if enabled():
        transaction.on_commit(_start)


def _start() -> None:
    global _running, _rerun
    with _lock:
        if _running:
            _rerun = True  # the running pass will go around once more and see the new rows
            return
        _running = True
    threading.Thread(target=_drain, name="notification-delivery", daemon=True).start()


def _drain() -> None:
    global _running, _rerun
    from .delivery import deliver_pending

    try:
        while True:
            with _lock:
                _rerun = False
            result = deliver_pending()
            log.info("notification delivery pass sent=%(sent)s failed=%(failed)s expired=%(expired)s", result)
            with _lock:
                if not _rerun:
                    _running = False
                    return
    except Exception:  # a worker thread must never die silently with the flag stuck on
        log.exception("notification dispatch: unexpected failure")
        with _lock:
            _running = False
    finally:
        connections.close_all()
