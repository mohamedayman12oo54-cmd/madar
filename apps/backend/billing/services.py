"""
BILL-WU-019 — checkout initiation service (ADR-016 trust boundary).

Checkout never activates the Subscription (only BILL-WU-021's verified-
event application may) and never marks a period paid: it only records
intent (the chosen plan and its server-side price) on a `PaymentAttempt`
and asks the payment provider for a hosted setup-session URL to redirect
the teacher to. The row lock on `Subscription` is held only for the local
decision-and-create step; the provider call happens after it is released
(ai-execution-guidance directive 15 — no outbound call inside a DB
transaction).

BILL-WU-028 — `cancel_subscription` below adds cancel-at-period-end. It
takes the SAME FIRST LOCK, in the same order, as the renewal claim
(`process_billing_renewals.claim_due_subscription`, BILL-WU-025): the
Subscription row via `select_for_update()`, before anything else. Neither
path ever acquires a second lock before releasing or committing that one,
so the two paths structurally cannot deadlock against each other (this
unit's own "Failure modes": "prevented by single lock order").

**Known gap, disclosed, not a `models.py` change** (same discipline as
every other worker in this plan): this unit's own "Expected outcome"
describes setting a `cancel_requested_at` timestamp alongside the flag,
but `Subscription` has no such field. `updated_at` (`auto_now`) already
records the moment the row was last written, which is this same moment
whenever the flag transitions — no new field is needed to answer "when
was this cancelled", and none is added.
"""
import dataclasses
import secrets
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from . import entitlements
from .models import PaymentAttempt, Plan, Subscription
from .providers import ProviderError, get_payment_provider


class CheckoutError(Exception):
    """A stable, client-facing checkout refusal. `code` is machine-readable."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(detail)


def _generate_merchant_order_id():
    # 256 bits of randomness (unguessable) and carries no environment id or
    # other forgeable identifier in its text (this unit's own
    # data-integrity considerations).
    return f"chk_{secrets.token_urlsafe(32)}"


def _get_or_create_subscription(environment):
    # Mirrors `financials/views.py`'s select_for_update/get_or_create retry
    # (the first-ever checkout for an Environment has no Subscription row
    # yet; two concurrent requests could both miss it and race to create
    # one, tripping the OneToOneField's uniqueness).
    for _ in range(2):
        try:
            with transaction.atomic():
                return Subscription.objects.select_for_update().get_or_create(environment=environment)
        except IntegrityError:
            continue
    # Unreachable in practice (the second attempt always finds the row the
    # other request created), kept only to satisfy "never loop forever".
    with transaction.atomic():
        return Subscription.objects.select_for_update().get_or_create(environment=environment)


def start_checkout(environment, plan_key, return_url):
    """Create (or resume) the non-terminal checkout `PaymentAttempt` for
    `environment` and ask the payment provider for a hosted session.
    Returns `(attempt, session_url)`. Raises `CheckoutError` on refusal."""
    try:
        plan = Plan.objects.get(key=plan_key, is_active=True)
    except Plan.DoesNotExist:
        raise CheckoutError("invalid_plan", "Unknown or inactive plan.")

    with transaction.atomic():
        subscription, _ = _get_or_create_subscription(environment)

        now = timezone.now()
        if (
            subscription.current_period_start is not None
            and subscription.current_period_end is not None
            and subscription.current_period_start <= now < subscription.current_period_end
        ):
            raise CheckoutError(
                "paid_period_active", "A paid period is already active; plan changes are not supported here."
            )

        attempt = (
            PaymentAttempt.objects.filter(
                subscription=subscription, billing_period__isnull=True,
                status__in=PaymentAttempt.NON_TERMINAL_STATUSES,
            )
            .order_by("-created_at")
            .first()
        )
        if attempt is None:
            subscription.plan = plan
            subscription.save(update_fields=["plan"])
            attempt = PaymentAttempt.objects.create(
                environment=environment, subscription=subscription,
                merchant_order_id=_generate_merchant_order_id(),
                amount_minor_units=plan.price_minor_units, currency=plan.currency,
                status=PaymentAttempt.Status.INITIATED,
            )

    # Outside the transaction above: the lock is released before this call.
    provider = get_payment_provider()
    try:
        session = provider.create_recurring_setup_session(attempt, plan, return_url)
    except ProviderError:
        PaymentAttempt.objects.filter(pk=attempt.pk).update(status=PaymentAttempt.Status.FAILED)
        raise CheckoutError("provider_unavailable", "Could not start checkout right now. Please try again.")

    PaymentAttempt.objects.filter(pk=attempt.pk).update(provider_order_id=session.provider_session_ref)
    attempt.provider_order_id = session.provider_session_ref
    return attempt, session.session_url


class CancelError(Exception):
    """A stable, client-facing cancellation refusal. `code` is machine-readable."""

    def __init__(self, code, detail):
        self.code = code
        self.detail = detail
        super().__init__(detail)


@dataclasses.dataclass(frozen=True)
class CancelResult:
    cancel_at_period_end: bool
    renewal_already_in_progress: bool
    renewal_attempt_status: Optional[str]


def cancel_subscription(environment):
    """Set `cancel_at_period_end=True` for `environment`'s Subscription.
    Idempotent: a repeat call re-locks the same row, finds the flag
    already set, and returns the same shape. Never touches
    `current_period_end`, never deletes anything, never issues a refund
    (this unit's own exclusions).

    Race-safety (this unit's own "Race-safety rule", normative): after
    locking, checks whether a non-terminal, period-bound `PaymentAttempt`
    already exists — the renewal claim's own double-charge guard
    (BILL-WU-008/025) means at most one such attempt can exist at a time,
    and its mere existence means a renewal claim for the NEXT period
    already committed before this call acquired the lock. The in-flight
    charge is never cancelled (Kashier can't be assumed to support
    aborting it) — this is surfaced to the caller, never hidden."""
    try:
        with transaction.atomic():
            subscription = Subscription.objects.select_for_update().get(environment=environment)
            subscription.cancel_at_period_end = True
            subscription.save(update_fields=["cancel_at_period_end"])

            in_progress = (
                PaymentAttempt.objects.filter(
                    subscription=subscription, billing_period__isnull=False,
                    status__in=PaymentAttempt.NON_TERMINAL_STATUSES,
                )
                .order_by("-created_at")
                .first()
            )
    except Subscription.DoesNotExist:
        raise CancelError("no_subscription", "No subscription exists for this environment.")

    return CancelResult(
        cancel_at_period_end=True,
        renewal_already_in_progress=in_progress is not None,
        renewal_attempt_status=in_progress.status if in_progress is not None else None,
    )


def get_checkout_status(environment, attempt_id):
    """Display-only lookup for the redirect-return page (ADR-016): never
    writes anything. Returns `None` if no such attempt exists for this
    environment (never raises, so a missing/forged id is just "nothing to
    show", not an error)."""
    if not attempt_id:
        return None
    return PaymentAttempt.objects.filter(pk=attempt_id, environment=environment).first()


def start_trial(*, environment, activated_at):
    """BILL-WU-014 — commercial-model §Free trial: 16 days, starting at
    the instant the Teacher Account is activated AND its Environment is
    established (one atomic signup event) — `activated_at` is the
    Backend's own `timezone.now()`, captured once by the caller, never a
    client-supplied timestamp. No payment method, no auto-conversion.

    Called from INSIDE `accounts`' own atomic signup transaction (BND-1:
    `accounts` calls this Billing capability; it never writes a Billing
    table itself). `environment` was just created in that SAME
    transaction, so this can never raise `IntegrityError` for an existing
    Subscription — that matters because the caller's surrounding
    `except IntegrityError` would otherwise mis-report this as its own
    "phone/email already in use" conflict (this unit's own data-integrity
    requirement).

    Sets both `trial_started_at` and `trial_ends_at`. `entitlements.decide()`
    (BILL-WU-010, already VERIFIED) derives the trial window from
    `trial_started_at` alone and never reads `trial_ends_at` — it is set
    here anyway, consistently, since the column already exists
    (BILL-WU-008) and nothing should have to guess whether it was meant
    to be populated."""
    trial_ends_at = activated_at + timezone.timedelta(days=entitlements.TRIAL_DAYS)
    return Subscription.objects.create(
        environment=environment, trial_started_at=activated_at, trial_ends_at=trial_ends_at,
    )
