"""
BILL-WU-023 — reconciliation of ambiguous/pending/missed payment-attempt
outcomes (ADR-016's second trusted path: "an internal reconciliation job
polling Kashier's own status-lookup API"). Same atomic-claim template as
BILL-WU-022's recovery worker, applied to `PaymentAttempt` instead of
`ProviderEvent`, and feeding any resolved outcome through the SAME shared
transition functions webhook events use (`events.apply_success`,
`transitions.record_confirmed_failure`) — "it does not use a second
state machine" (this unit's own wording; see `events.py`'s own module
docstring for the disclosed refactor that made `apply_success` public
and reusable here).

    python manage.py reconcile_billing_attempts
    python manage.py reconcile_billing_attempts --min-age-minutes 10 --abandon-age-minutes 1440
    python manage.py reconcile_billing_attempts --loop --interval 30

Unlike the receipt-time webhook path, the lookup call to
`provider.lookup_order(...)` happens OUTSIDE any transaction (this
unit's own "Data-integrity & security considerations"); applying its
result reuses functions that are each independently safe under
concurrency (AC-BILL-023-5) — a second reconciler's conditional UPDATE
simply matches zero rows, so no explicit claim step is needed here
(unlike BILL-WU-022's `ProviderEvent` worker, `PaymentAttempt.status` is
read by other modules — `entitlements`, `services.start_checkout` — so
introducing an extra ad-hoc "reconciling" value here was deliberately
avoided to not risk those other call sites misreading it).

**Known gap, disclosed, not a `models.py` change** (same discipline as
BILL-WU-021/022/029's own disclosed gaps): `PaymentAttempt.Status` has no
dedicated "abandoned"/"expired" member. An abandoned checkout attempt
(AC-BILL-023-4) is recorded via the existing `failed` status, using the
SAME `transitions.record_confirmed_failure` function a genuine payment
failure uses — semantically defensible (an abandoned checkout IS a
failure to complete, from the system's perspective) and, critically,
`failed` is already excluded from `PaymentAttempt.NON_TERMINAL_STATUSES`,
so `billing.services.start_checkout`'s existing non-terminal-attempt
check (BILL-WU-019) already treats it as done and lets a new checkout
start — satisfying AC-4's second half with zero new code.
"""
import argparse
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from billing import events
from billing.models import PaymentAttempt
from billing.providers import get_payment_provider
from billing.transitions import record_confirmed_failure

# Operational settings for this job's own safety/timing, not commercial
# numbers (ai-execution-guidance directive 4; BILL-DEC-05 is a different,
# still-open number and is not read here).
DEFAULT_MIN_AGE_MINUTES = 10
DEFAULT_ABANDON_AGE_MINUTES = 24 * 60


def _reconcile_one(attempt, provider, abandon_before):
    """Returns `"resolved"`, `"abandoned"` or `"unresolved"`."""
    lookup = provider.lookup_order(attempt.merchant_order_id)  # OUTSIDE any transaction

    if lookup.outcome == "succeeded":
        events.apply_success(
            attempt, provider_transaction_id=lookup.provider_transaction_id,
            provider_order_id=lookup.provider_order_id,
        )
        return "resolved"
    if lookup.outcome == "failed":
        record_confirmed_failure(attempt, provider_code=lookup.raw_code)
        return "resolved"

    # Inconclusive (pending/unknown): an old-enough checkout attempt is
    # abandoned/expired (AC-4); a renewal attempt stays unresolved and
    # blocks a new charge for its period (AC-2's own DB constraint,
    # BILL-WU-008) until this job, BILL-WU-025, or a human resolves it.
    if attempt.billing_period_id is None and attempt.created_at < abandon_before:
        record_confirmed_failure(attempt, provider_code="abandoned")
        return "abandoned"
    # Alerted only via this command's own stdout for now — no
    # notification channel exists yet (BILL-DEC-06).
    return "unresolved"


class Command(BaseCommand):
    help = "Reconciles PENDING/UNKNOWN billing payment attempts via provider.lookup_order."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--min-age-minutes", type=int, default=DEFAULT_MIN_AGE_MINUTES)
        parser.add_argument("--abandon-age-minutes", type=int, default=DEFAULT_ABANDON_AGE_MINUTES)
        parser.add_argument("--loop", action="store_true", help="Keep running, polling for new work.")
        parser.add_argument("--interval", type=float, default=30.0, help="Seconds between polls in --loop mode.")
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
        now = timezone.now()
        old_enough = now - timedelta(minutes=options["min_age_minutes"])
        abandon_before = now - timedelta(minutes=options["abandon_age_minutes"])

        provider = get_payment_provider()
        candidate_ids = list(
            PaymentAttempt.objects.filter(
                status__in=(PaymentAttempt.Status.PENDING, PaymentAttempt.Status.UNKNOWN),
                created_at__lt=old_enough,
            ).order_by("created_at").values_list("id", flat=True)[: options["limit"]]
        )

        resolved = abandoned = unresolved = 0
        for attempt_id in candidate_ids:
            # Re-check it is still non-terminal: a webhook (or another
            # reconciler) may have already resolved it since the
            # unlocked selection above.
            attempt = PaymentAttempt.objects.filter(
                pk=attempt_id, status__in=PaymentAttempt.NON_TERMINAL_STATUSES
            ).first()
            if attempt is None:
                continue

            outcome = _reconcile_one(attempt, provider, abandon_before)
            if outcome == "resolved":
                resolved += 1
            elif outcome == "abandoned":
                abandoned += 1
            else:
                unresolved += 1

        self.stdout.write(self.style.SUCCESS(
            f"Reconciled {resolved + abandoned + unresolved} billing attempt(s): "
            f"{resolved} resolved, {abandoned} abandoned, {unresolved} still unresolved."
        ))
