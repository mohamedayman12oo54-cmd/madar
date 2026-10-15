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
"""
import secrets

from django.db import IntegrityError, transaction
from django.utils import timezone

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


def get_checkout_status(environment, attempt_id):
    """Display-only lookup for the redirect-return page (ADR-016): never
    writes anything. Returns `None` if no such attempt exists for this
    environment (never raises, so a missing/forged id is just "nothing to
    show", not an error)."""
    if not attempt_id:
        return None
    return PaymentAttempt.objects.filter(pk=attempt_id, environment=environment).first()
