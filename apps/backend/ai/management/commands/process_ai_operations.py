"""
Phase 5 async worker for AI operations — the "management-command worker
inside the same Django codebase" the V1 architecture sanctions (no broker).
Run repeatedly (cron/systemd timer/loop) outside the request cycle.

    python manage.py process_ai_operations
    python manage.py process_ai_operations --limit 20 --requeue-stale-minutes 15
    python manage.py process_ai_operations --loop --interval 2      # long-running

Safety properties:
- CLAIMING IS ATOMIC. A pending row is claimed with a single conditional
  UPDATE (pending -> processing); if two workers race for the same row, only
  one UPDATE matches and the other skips it — an operation is never sent to
  the provider twice.
- The (slow) provider call happens OUTSIDE any transaction/lock.
- The outcome is persisted in Madar's own table; nothing else is written, so
  a failure can never leave partial state behind.
- A worker that dies mid-call leaves a row stuck in `processing`; rows older
  than --requeue-stale-minutes are put back to `pending`.
"""
import argparse
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ai.models import AIOperation
from ai.providers import AIProviderError, get_provider


def claim(op_id: int) -> bool:
    """Atomically move ONE operation pending -> processing. A single
    conditional UPDATE: of any number of concurrent callers, exactly one
    sees a matching row and gets True."""
    return bool(
        AIOperation.objects.filter(pk=op_id, status=AIOperation.Status.PENDING).update(
            status=AIOperation.Status.PROCESSING, started_at=timezone.now()
        )
    )


class Command(BaseCommand):
    help = "Processes PENDING AI operations via the configured provider."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--requeue-stale-minutes", type=int, default=15)
        parser.add_argument("--loop", action="store_true", help="Keep running, polling for new work.")
        parser.add_argument("--interval", type=float, default=2.0, help="Seconds between polls in --loop mode.")
        parser.add_argument("--max-iterations", type=int, default=0, help=argparse.SUPPRESS)

    def handle(self, *args, **options):
        iteration = 0
        while True:
            self.run_once(options)
            iteration += 1
            if not options["loop"] or (options["max_iterations"] and iteration >= options["max_iterations"]):
                break
            time.sleep(options["interval"])

    def run_once(self, options):
        stale_before = timezone.now() - timedelta(minutes=options["requeue_stale_minutes"])
        requeued = AIOperation.objects.filter(
            status=AIOperation.Status.PROCESSING, started_at__lt=stale_before
        ).update(status=AIOperation.Status.PENDING, started_at=None)

        completed = failed = 0
        pending_ids = list(
            AIOperation.objects.filter(status=AIOperation.Status.PENDING)
            .order_by("created_at").values_list("id", flat=True)[: options["limit"]]
        )
        for op_id in pending_ids:
            if not claim(op_id):
                continue  # another worker got it
            op = AIOperation.objects.get(pk=op_id)
            try:
                result = get_provider().generate(op.prompt)
            except Exception as exc:  # any provider failure -> explicit `failed`
                message = str(exc) if isinstance(exc, AIProviderError) else "تعذّر إكمال الطلب."
                op.status = AIOperation.Status.FAILED
                op.error = message[:255]
                op.result = ""
                failed += 1
            else:
                op.status = AIOperation.Status.COMPLETED
                op.result = result
                op.error = ""
                completed += 1
            op.completed_at = timezone.now()
            op.save(update_fields=["status", "result", "error", "completed_at"])

        self.stdout.write(self.style.SUCCESS(
            f"Processed {completed + failed} AI operation(s): {completed} completed, {failed} failed"
            + (f"; requeued {requeued} stale." if requeued else ".")
        ))
