"""
BILL-WU-025 — renewal execution capability. Madar owns the billing
schedule (Kashier has no managed subscriptions): this worker charges the
saved recurring agreement once per due period. This is the
**capability**; BILL-WU-026 is the **gate** that enables it for real
charges in production, via `settings.BILLING_RENEWALS_LIVE_ENABLED`.

    python manage.py process_billing_renewals
    python manage.py process_billing_renewals --limit 20 --requeue-stale-minutes 30
    python manage.py process_billing_renewals --loop --interval 60

Modeled on `ai/management/commands/process_ai_operations.py`'s claim/
call-outside-lock/persist pattern, with ONE deliberate difference this
unit's own spec calls out: a worker that crashes after claiming never
requeues to a retryable state — it is swept to `unknown` for
reconciliation (BILL-WU-023), never blindly retried, because a re-charge
could double-bill. Double-charge prevention here has three independent
layers: (1) the claim transaction re-checks `cancel_at_period_end` and
`renewal_due` under the Subscription row lock, so a losing concurrent
worker sees the winner's already-advanced period and skips; (2) the
`(subscription, period_start)` unique constraint (BILL-WU-008) would
reject a duplicate period even if (1) somehow didn't catch it; (3) the
partial unique index on `PaymentAttempt` (one non-terminal attempt per
`BillingPeriod`, BILL-WU-008) means a stale attempt swept to `unknown`
still blocks a second attempt for the same period — it is NON_TERMINAL
BY THIS MODEL'S OWN DEFINITION — until reconciliation resolves it.

**Known gap, disclosed, not a `models.py` change** (same discipline as
every other worker in this plan): this unit's own "Expected outcome"
describes creating a `PaymentAttempt` with status `processing`, but
`PaymentAttempt.Status` has no such member. Using `initiated` instead —
already a legitimate "freshly created, not yet resolved" status (the
same one a checkout attempt starts in) and already a member of
`NON_TERMINAL_STATUSES`, so every existing structural guard (the partial
unique index, `services.start_checkout`'s own non-terminal check)
already treats it correctly with zero new code. The one thing this
means: the stale-sweep below only ever touches an `initiated` attempt
that ALSO has `billing_period_id` set (a renewal attempt it created) —
never a checkout attempt's `initiated` state (which legitimately stays
`initiated`, sometimes for a long time, while waiting on the customer's
redirect/webhook; `billing_period_id` is always null for those, so they
are never swept).
"""
import argparse
import secrets
import time
from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from billing import events, periods
from billing.models import AmountOwed, BillingPeriod, PaymentAttempt, Subscription
from billing.providers import ProviderError, get_payment_provider
from billing.transitions import record_confirmed_failure

DEFAULT_REQUEUE_STALE_MINUTES = 30


def _generate_merchant_order_id():
    # Unguessable, no environment id or other forgeable identifier
    # encoded (same discipline as `services._generate_merchant_order_id`,
    # not imported directly since that helper is private to that module).
    return f"renew_{secrets.token_urlsafe(32)}"


def live_mode_disabled():
    """True when a real charge must never happen: `KASHIER_MODE=live`
    and the kill switch is off. Checked at command start and again
    before every single charge (defense in depth, per this unit's own
    "Data-integrity & security considerations")."""
    return settings.KASHIER_MODE == "live" and not settings.BILLING_RENEWALS_LIVE_ENABLED


def claim_due_subscription(subscription_id, now):
    """One atomic transaction, Subscription row locked first (this
    unit's own lock order). Re-reads `cancel_at_period_end` and
    `renewal_due` under the lock — a losing concurrent worker reaches
    this after the winner's transaction has already committed and
    advanced the period, so `renewal_due` is now false and it skips.
    Returns the new `PaymentAttempt`, or `None` if skipped."""
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(pk=subscription_id)
        if subscription.cancel_at_period_end or subscription.active_agreement_id is None:
            return None
        if not periods.renewal_due(subscription, now):
            return None
        if PaymentAttempt.objects.filter(
            subscription=subscription, status__in=PaymentAttempt.NON_TERMINAL_STATUSES
        ).exists():
            return None

        current = periods.current_period(subscription, now)
        start, end = periods.next_period(current.period_end if current is not None else now)
        plan = subscription.plan  # price FROM THE PLAN ROW AT THIS MOMENT — price-change policy is OUT OF SCOPE (BILL-WU-042)

        period = BillingPeriod.objects.create(
            environment=subscription.environment, subscription=subscription, period_start=start, period_end=end,
        )
        AmountOwed.objects.create(
            environment=subscription.environment, billing_period=period,
            amount_minor_units=plan.price_minor_units, currency=plan.currency, status=AmountOwed.Status.OPEN,
        )
        attempt = PaymentAttempt.objects.create(
            environment=subscription.environment, subscription=subscription, billing_period=period,
            merchant_order_id=_generate_merchant_order_id(),
            amount_minor_units=plan.price_minor_units, currency=plan.currency,
            status=PaymentAttempt.Status.INITIATED,
        )
        return attempt


class Command(BaseCommand):
    help = "Charges saved recurring agreements for due Subscriptions (one attempt per period)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=20)
        parser.add_argument("--requeue-stale-minutes", type=int, default=DEFAULT_REQUEUE_STALE_MINUTES)
        parser.add_argument("--loop", action="store_true", help="Keep running, polling for new work.")
        parser.add_argument("--interval", type=float, default=60.0, help="Seconds between polls in --loop mode.")
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
        if live_mode_disabled():
            self.stdout.write(self.style.WARNING(
                "Live billing renewals are disabled (KASHIER_MODE=live, "
                "BILLING_RENEWALS_LIVE_ENABLED=False) — charging nothing this run."
            ))
            return

        now = timezone.now()
        stale_before = now - timedelta(minutes=options["requeue_stale_minutes"])
        # A worker that crashed after claiming (possibly after charging)
        # is swept to `unknown`, never requeued to a retryable state —
        # re-charging could double-bill. Only ever touches a RENEWAL
        # attempt (`billing_period` set); a checkout attempt's own
        # `initiated` state is untouched (see module docstring).
        requeued = PaymentAttempt.objects.filter(
            status=PaymentAttempt.Status.INITIATED, billing_period__isnull=False, updated_at__lt=stale_before,
        ).update(status=PaymentAttempt.Status.UNKNOWN)

        candidate_ids = list(
            Subscription.objects.filter(
                state=Subscription.State.ACTIVE, cancel_at_period_end=False, active_agreement__isnull=False,
            ).order_by("pk").values_list("id", flat=True)
        )

        charged = skipped = 0
        provider = get_payment_provider()
        for subscription_id in candidate_ids[: options["limit"]]:
            if live_mode_disabled():
                break

            attempt = claim_due_subscription(subscription_id, now)
            if attempt is None:
                skipped += 1
                continue

            agreement_ref = attempt.subscription.active_agreement.card_token

            # OUTSIDE any transaction (AC-7) — the slow external call.
            try:
                result = provider.charge_saved_agreement(attempt, agreement_ref)
            except ProviderError:
                result = None  # a transport failure is ambiguous, never a confirmed failure

            if result is None or result.outcome in ("pending", "unknown"):
                PaymentAttempt.objects.filter(pk=attempt.pk, status=PaymentAttempt.Status.INITIATED).update(
                    status=PaymentAttempt.Status.UNKNOWN if result is None or result.outcome == "unknown"
                    else PaymentAttempt.Status.PENDING
                )
            elif result.outcome == "succeeded":
                events.apply_success(
                    attempt, provider_transaction_id=result.provider_transaction_id,
                    provider_order_id=result.provider_order_id,
                )
            else:  # "failed"
                record_confirmed_failure(attempt, provider_code=result.raw_code)

            charged += 1

        self.stdout.write(self.style.SUCCESS(
            f"Processed {charged + skipped} due subscription(s): {charged} charged, {skipped} skipped"
            + (f"; requeued {requeued} stale." if requeued else ".")
        ))
