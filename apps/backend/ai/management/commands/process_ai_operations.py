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

BILL-WU-011 (OP-PARITY): the submit-time entitlement check (billing's
`RequiresCapability` permission) does not guarantee the Environment is
still entitled by the time this worker actually picks the row up — a
renewal can fail, or a cancellation's period can end, in between. For the
two plan-gated kinds, this worker re-checks `billing.entitlements.decide`
right after claiming and before any provider call; a lost capability ends
the operation `failed` with a stable error, same as any other failure
(ADR-006 "no partial result" — no Quiz row, no suggested_state). The
`assistant` kind is never checked here either, mirroring the views' own
not-gated-until-BILL-DEC-07 stance. Context is reconstructed from
`op.environment_id` alone (server-created state), so this worker needs no
request/session — satisfying OP-PARITY without duplicating the Web path's
own check.
"""
import argparse
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from ai.models import AIOperation
from ai.processing import COMPLETED, ENTITLEMENT_LOST_ERROR, GATED_KIND_CAPABILITIES, claim, run_claimed  # noqa: F401


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
                continue  # another worker (or the in-process dispatcher) got it
            if run_claimed(op_id) == COMPLETED:
                completed += 1
            else:
                failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed {completed + failed} AI operation(s): {completed} completed, {failed} failed"
            + (f"; requeued {requeued} stale." if requeued else ".")
        ))
