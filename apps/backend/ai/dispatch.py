"""
Starts an AI operation the moment its request is saved, inside this process, instead of waiting for someone to
run `process_ai_operations`.

Why: before this module an operation sat `pending` until a separate worker process happened to poll — if nobody
ran one, the Study Assistant and "quiz me" never answered at all, and even with one the student waited for its
polling interval on top of the model's own time.

How it stays safe (nothing about the lifecycle changes):
* the work still goes through `ai.processing.claim()`, one conditional UPDATE, so a row is processed exactly once
  however many threads, processes or `process_ai_operations` workers race for it;
* it is started with `transaction.on_commit`, so a request that rolls back never starts work for a row that does
  not exist;
* a small bounded pool (AI_INLINE_WORKERS) keeps a burst of requests from opening dozens of provider calls at once;
  the rest simply wait in the pool queue as `pending` rows;
* if the process dies mid-call the row is put back by the stale sweep below (and by the command), never lost.

`AI_WORKER_MODE=external` turns it off and leaves everything to the command (cron / `--loop`), the earlier
behaviour. The two can run together.
"""
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from django.conf import settings
from django.db import connections, transaction
from django.utils import timezone

log = logging.getLogger(__name__)

SWEEP_EVERY_SECONDS = 60
PENDING_GRACE_SECONDS = 30       # a pending row older than this was missed by its own dispatch
DEFAULT_WORKERS = 4

_lock = threading.Lock()
_executor = None
_last_sweep = 0.0


def enabled() -> bool:
    return getattr(settings, "AI_WORKER_MODE", "external") == "thread"


def _pool():
    global _executor
    with _lock:
        if _executor is None:
            workers = max(1, int(getattr(settings, "AI_INLINE_WORKERS", DEFAULT_WORKERS)))
            _executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="ai-op")
        return _executor


def _release_connections():
    """A pool thread owns its own DB connections; give them back after every job so none is left open behind
    an idle thread (which would also stop the test database from being dropped)."""
    connections.close_all()


def _run(op_id):
    from .processing import process_operation

    try:
        process_operation(op_id)
        _sweep()
    except Exception:  # never let a worker thread die silently with the row stuck in `processing`
        log.exception("ai dispatch: unexpected failure op=%s", op_id)
    finally:
        _release_connections()


def _sweep(now=None):
    """Put crashed work back and pick up rows whose dispatch was lost (process restarted, pool refused, ...).
    Throttled, so it costs two cheap queries per minute at most."""
    global _last_sweep
    mono = time.monotonic()
    with _lock:
        if mono - _last_sweep < SWEEP_EVERY_SECONDS:
            return
        _last_sweep = mono
    from .models import AIOperation

    now = now or timezone.now()
    AIOperation.objects.filter(
        status=AIOperation.Status.PROCESSING, started_at__lt=now - timedelta(minutes=15),
    ).update(status=AIOperation.Status.PENDING, started_at=None)
    missed = list(
        AIOperation.objects.filter(
            status=AIOperation.Status.PENDING, created_at__lt=now - timedelta(seconds=PENDING_GRACE_SECONDS),
        ).order_by("created_at").values_list("id", flat=True)[:20]
    )
    for op_id in missed:
        _pool().submit(_safe_process, op_id)


def _safe_process(op_id):
    from .processing import process_operation

    try:
        process_operation(op_id)
    except Exception:
        log.exception("ai dispatch: sweep failure op=%s", op_id)
    finally:
        _release_connections()


def dispatch(op_id):
    """Call right after creating an operation. A no-op unless AI_WORKER_MODE=thread."""
    if not enabled():
        return
    transaction.on_commit(lambda: _pool().submit(_run, op_id))
