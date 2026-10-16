"""
BILL-WU-022 — recovery worker for billing provider events (ADR-017's
"recovery after interruption" leg). Modeled on
`ai/management/commands/process_ai_operations.py`'s claim/call/record
pattern.

    python manage.py process_billing_events
    python manage.py process_billing_events --limit 20 --requeue-stale-minutes 15
    python manage.py process_billing_events --loop --interval 2      # long-running

Unlike `process_ai_operations.py`, `billing.events.apply()` makes no slow
external call — it is a short, self-contained DB transaction (BILL-WU-021).
So the claim step here exists only to (a) make two concurrent runs never
count the same event as two separate "attempts" against the
`--max-attempts` budget, and (b) detect a worker that crashed between
claiming an event and `apply()` finishing, not to guard a slow call.

**Known gaps, disclosed, not a `models.py` change (outside this unit's
own "Implementation surfaces" — this command file only):**
- `ProviderEvent.processing_status` (BILL-WU-008) is a plain `CharField`
  with no DB-level `CHECK` constraint restricting it to
  `ProviderEvent.ProcessingStatus`'s declared members (only Django's own,
  unused-here, `full_clean()`/forms validation would enforce that). This
  worker writes one ad-hoc value the model's enum does not yet declare,
  `"processing"` (`PROCESSING` below), to mark a claimed-but-unresolved
  event. `events.py` was given a small, disclosed, behavior-preserving
  change (see its own module docstring) so this value is not mistaken
  for "already resolved". A genuinely poison event (exceeds
  `--max-attempts`) is recorded as the model's own, already-declared
  `failed_to_apply` with a `last_error` naming it `needs_attention` —
  no second ad-hoc value was needed for that one.
- There is no dedicated "claimed at" timestamp field (`AIOperation` has
  `started_at`; `ProviderEvent` has only the immutable `received_at`, set
  once at receipt). The stale-requeue sweep below uses `received_at` as
  an approximation: this can reclaim a just-claimed event sooner than
  `--requeue-stale-minutes` after its actual claim (if the event was
  received long before being claimed), but never later, and reclaiming
  early is safe here (`events.apply()`'s own internal row lock makes a
  redundant concurrent claim harmless — see AC-BILL-022-2's own test).
"""
import argparse
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import events
from billing.models import ProviderEvent

# Not a declared `ProviderEvent.ProcessingStatus` member (see module
# docstring) — this worker's own transient "claimed, not yet resolved"
# marker.
PROCESSING = "processing"

# Operational setting for this job's own safety net, not a commercial
# retry policy (ai-execution-guidance directive 4; BILL-DEC-05 is a
# different, still-open number and is not read here).
DEFAULT_MAX_ATTEMPTS = 5


def claim(event_id: int) -> bool:
    """Atomically move ONE event `received` -> the worker's own
    `processing` marker. A single conditional UPDATE: of any number of
    concurrent callers, exactly one sees a matching row and gets True."""
    return bool(
        ProviderEvent.objects.filter(pk=event_id, processing_status=ProviderEvent.ProcessingStatus.RECEIVED)
        .update(processing_status=PROCESSING)
    )


class Command(BaseCommand):
    help = "Applies RECEIVED (and stale claimed) billing provider events via billing.events.apply."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--requeue-stale-minutes", type=int, default=15)
        parser.add_argument("--max-attempts", type=int, default=DEFAULT_MAX_ATTEMPTS)
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
        requeued = ProviderEvent.objects.filter(
            processing_status=PROCESSING, received_at__lt=stale_before
        ).update(processing_status=ProviderEvent.ProcessingStatus.RECEIVED)

        applied = failed = 0
        candidate_ids = list(
            ProviderEvent.objects.filter(processing_status=ProviderEvent.ProcessingStatus.RECEIVED)
            .order_by("received_at").values_list("id", flat=True)[: options["limit"]]
        )
        for event_id in candidate_ids:
            if not claim(event_id):
                continue  # another worker got it

            event = ProviderEvent.objects.get(pk=event_id)
            error = ""
            try:
                events.apply(event)
            except Exception as exc:  # a poison event must never stop the batch
                error = str(exc)[:255]

            event.refresh_from_db()
            if event.processing_status != PROCESSING:
                # events.apply() resolved it one way or another (processed,
                # failed_to_apply, or left intentionally received — e.g. a
                # refund event, BILL-WU-021's own documented outcome).
                applied += 1
                continue

            # Still claimed: apply() raised, or (defensively) returned
            # without reaching its own terminal write. Count an attempt.
            new_attempts = event.attempts_count + 1
            if new_attempts >= options["max_attempts"]:
                ProviderEvent.objects.filter(pk=event_id).update(
                    processing_status=ProviderEvent.ProcessingStatus.FAILED_TO_APPLY,
                    attempts_count=new_attempts,
                    last_error=f"needs_attention: exceeded {options['max_attempts']} attempts; last error: {error}"[:255],
                )
            else:
                ProviderEvent.objects.filter(pk=event_id).update(
                    processing_status=ProviderEvent.ProcessingStatus.RECEIVED,
                    attempts_count=new_attempts, last_error=error,
                )
            failed += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed {applied + failed} billing event(s): {applied} resolved, {failed} not yet resolved"
            + (f"; requeued {requeued} stale." if requeued else ".")
        ))
