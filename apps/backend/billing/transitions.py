"""
BILL-WU-029 — failed-payment outcome recording foundation (ADR-017).

Separates the decided foundation from the undecided numbers (BILL-DEC-05):
this module persists every attempt outcome and distinguishes a
**confirmed failure** (provider `FAILURE` or a definitive decline code)
from an **ambiguous** outcome (timeout, transport error, `PENDING`,
inconclusive lookup) — but schedules no retry and sets no grace deadline
(that is BILL-WU-030's job, gated on BILL-DEC-05's still-open numbers).
Used by BILL-WU-021 (webhook), BILL-WU-023 (reconciliation) and
BILL-WU-025 (renewal), none of which exist yet.

**Known gap, disclosed, not silently defaulted:** this unit's own
"Expected outcome" also calls for storing the provider's response code
and bilingual failure message on the attempt, and tracking
`first_failed_at`/a failure count on the Subscription. BILL-WU-008 (the
persistence foundation, already VERIFIED) never added fields for any of
these — `PaymentAttempt` has no code/message field, and `Subscription` has
no failure-tracking field. Adding them would mean changing `models.py`
and a migration, which is outside this unit's own "Implementation
surfaces" (`billing/services.py` or `billing/transitions.py` — explicitly
not `models.py`) and "In-scope changes" ("Transition functions, tests").
None of this unit's acceptance criteria (AC-BILL-029-1..4) actually
requires that storage, so `record_confirmed_failure` accepts
`provider_code`/`message` for forward-compatible call-site parity with
this unit's documented signature, and deliberately does not persist them.
A future unit that adds those fields can wire this up without changing
this function's signature.
"""
from django.db import transaction

from . import audit
from .models import PaymentAttempt, Subscription


def record_confirmed_failure(attempt, provider_code="", message=""):
    """AC-BILL-029-1, AC-BILL-029-4. `provider_code`/`message` are accepted
    for signature parity with this unit's own spec; see the module
    docstring for why they are not yet persisted."""
    with transaction.atomic():
        # Terminal-state precedence (AC-4): the conditional UPDATE only
        # matches a still-non-terminal attempt, so a failure arriving after
        # a success (or another failure) for the same attempt is a no-op.
        previous_status = attempt.status
        updated = PaymentAttempt.objects.filter(
            pk=attempt.pk, status__in=PaymentAttempt.NON_TERMINAL_STATUSES
        ).update(status=PaymentAttempt.Status.FAILED)
        if not updated:
            return

        attempt.status = PaymentAttempt.Status.FAILED
        audit.record_transition(
            environment=attempt.environment, model_name="payment_attempt", object_id=attempt.pk,
            field="status", from_value=previous_status, to_value=PaymentAttempt.Status.FAILED,
            actor="transitions.record_confirmed_failure",
        )
        # `provider_code` is a provider-chosen string of unknown shape
        # (this unit's own "Failure modes": a secret could leak via an
        # error path) — never logged verbatim; only that a failure
        # happened, and for which attempt.
        audit.log("attempt_outcome", merchant_order_id=attempt.merchant_order_id, outcome="failed")
        if attempt.billing_period_id is not None:
            # Renewal: mark the subscription payment-failed. Access is
            # unchanged by this — `entitlements.decide()` already keeps a
            # BillingPeriod with a failed-and-not-succeeded attempt granted
            # (`Basis.PAYMENT_FAILED_PENDING_POLICY`), independently of
            # `Subscription.state`, so AC-1's "entitlement stays granted"
            # holds without this module touching entitlements at all.
            previous_sub_state = Subscription.objects.filter(pk=attempt.subscription_id).values_list(
                "state", flat=True
            ).first()
            Subscription.objects.filter(pk=attempt.subscription_id).update(state=Subscription.State.PAST_DUE)
            if previous_sub_state is not None and previous_sub_state != Subscription.State.PAST_DUE:
                audit.record_transition(
                    environment=attempt.environment, model_name="subscription", object_id=attempt.subscription_id,
                    field="state", from_value=previous_sub_state, to_value=Subscription.State.PAST_DUE,
                    actor="transitions.record_confirmed_failure",
                )
        # For a checkout attempt (`billing_period` is null): nothing
        # changes on the subscription — the teacher may simply retry
        # checkout (this unit's own documented outcome).


def record_ambiguous(attempt):
    """AC-BILL-029-2. An ambiguous outcome (timeout, transport error,
    `PENDING`, inconclusive lookup) is never recorded as a failure — the
    attempt is left `unknown` (the model's own documented holding state
    "needs reconciliation"), and nothing on the Subscription changes."""
    with transaction.atomic():
        previous_status = attempt.status
        updated = PaymentAttempt.objects.filter(
            pk=attempt.pk, status__in=PaymentAttempt.NON_TERMINAL_STATUSES
        ).update(status=PaymentAttempt.Status.UNKNOWN)
        if updated and previous_status != PaymentAttempt.Status.UNKNOWN:
            audit.record_transition(
                environment=attempt.environment, model_name="payment_attempt", object_id=attempt.pk,
                field="status", from_value=previous_status, to_value=PaymentAttempt.Status.UNKNOWN,
                actor="transitions.record_ambiguous",
            )
            audit.log("attempt_outcome", merchant_order_id=attempt.merchant_order_id, outcome="ambiguous")
