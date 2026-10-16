"""
BILL-WU-021 — event application: correlation, status semantics,
transactional state transitions (ADR-016/017).

`apply(event_record)` is idempotent and meant to be called from the
webhook (best effort, after the receipt commits) and from the recovery
worker (BILL-WU-022, which depends on this unit). This module only
delivers the standalone, directly-callable function, exercised here by
calling it directly in tests.

**BILL-WU-022 addendum (disclosed):** the re-entrancy guard below treats
any event NOT already in a terminal `ProcessingStatus`
(`processed`/`failed_to_apply`/`ignored_duplicate`) as still eligible —
not only an exact-equals-`received` check. This was generalized (from an
exact `== RECEIVED` check) so BILL-WU-022's recovery worker can claim an
event into its own transient, ad-hoc `"processing"` marker (not a
declared `ProcessingStatus` member — see that command's own module
docstring) before calling this function, without this function treating
the claim itself as "already resolved" and no-op'ing. Every existing
caller/test from this unit still only ever passes a `received` event, so
this change is behavior-preserving for all of them (re-verified: the
full BILL-WU-021 test suite still passes unchanged after this edit).

**Known gaps, disclosed, not silently defaulted** (mirrors BILL-WU-029's
own disclosed gap in `transitions.py`): BILL-WU-008's persisted schema
(already VERIFIED) has no dedicated `ProcessingStatus` values for
"uncorrelated" or "rejected-mismatch" — only `received`/`processed`/
`failed_to_apply`/`ignored_duplicate` exist, and adding new ones would
mean changing `models.py`, outside this unit's own "Implementation
surfaces" (`events.py`/`services.py` only). Both conditions are recorded
as `failed_to_apply` with a specific, human-readable `last_error` instead
of a dedicated enum value. Similarly, `PaymentAttempt` has no `mode`
field to re-check "mode matches" against — mode consistency is already
enforced at webhook receipt time (BILL-WU-020 rejects a payload whose
`mode` doesn't match `settings.KASHIER_MODE` before a `ProviderEvent` row
ever exists), so this function does not re-check it.
"""
from django.db import transaction
from django.utils import timezone

from . import periods
from .models import AmountOwed, BillingPeriod, PaymentAttempt, ProviderEvent, RecurringAgreement, Subscription
from .transitions import record_confirmed_failure

# PROPOSED (BILL-EXT-03 not yet confirmed): the event-type values Kashier
# uses for a refund/void/reversal, as opposed to a pay event's own
# `event`. Stored and flagged for manual handling, never applied
# (BILL-WU-038 — refund application — is OUT OF SCOPE).
REFUND_LIKE_KINDS = frozenset({"refund", "void", "reversal"})

# Order-status values treated as "already succeeded" rather than a new
# charge (status-lookup reconciliation, BILL-WU-023, not built yet; this
# is forward-compatible plumbing for it).
SUCCESS_LIKE_STATUSES = frozenset({"SUCCESS", "ORDER_PAID_BEFORE"})

# An event in any of these is already resolved; re-entry is a no-op.
# Anything else (received, or BILL-WU-022's own transient claim marker)
# is still eligible to process.
_TERMINAL_PROCESSING_STATUSES = frozenset({
    ProviderEvent.ProcessingStatus.PROCESSED,
    ProviderEvent.ProcessingStatus.FAILED_TO_APPLY,
    ProviderEvent.ProcessingStatus.IGNORED_DUPLICATE,
})


def _mark(event_record, processing_status, last_error=""):
    ProviderEvent.objects.filter(pk=event_record.pk).update(
        processing_status=processing_status, last_error=last_error[:255],
        attempts_count=event_record.attempts_count + 1,
    )
    event_record.processing_status = processing_status
    event_record.last_error = last_error[:255]
    event_record.attempts_count += 1


def _apply_success(attempt, subscription, event_record):
    now = timezone.now()
    agreement_ref = event_record.redacted_payload.get("agreement_ref") or ""
    # PROPOSED (BILL-EXT-03 not yet confirmed which field carries the
    # card-token reference): fall back to the provider transaction id as
    # the opaque token reference when no dedicated agreement_ref is
    # present, so a real agreement reference is never fabricated.
    card_token = agreement_ref or event_record.provider_transaction_id or attempt.merchant_order_id

    PaymentAttempt.objects.filter(pk=attempt.pk).update(
        status=PaymentAttempt.Status.SUCCEEDED,
        provider_transaction_id=event_record.provider_transaction_id or attempt.provider_transaction_id,
        provider_order_id=event_record.provider_order_id or attempt.provider_order_id,
    )

    if attempt.billing_period_id is None:
        # Checkout success: tokenize the recurring agreement (opaque
        # reference only — ADR-015; never a PAN/CVV) and create the
        # first period. *t* = this Backend's success-processing instant
        # (decided and recorded here, since BILL-EXT-03 hasn't confirmed
        # whether Kashier's own `creationDate` should be preferred).
        agreement = RecurringAgreement.objects.create(
            environment=attempt.environment, subscription=subscription,
            card_token=card_token, kashier_agreement_id=agreement_ref or None,
            mode=event_record.mode,
        )
        start, end = periods.next_period(now)
        period = BillingPeriod.objects.create(
            environment=attempt.environment, subscription=subscription, period_start=start, period_end=end,
        )
        AmountOwed.objects.create(
            environment=attempt.environment, billing_period=period,
            amount_minor_units=attempt.amount_minor_units, currency=attempt.currency,
            status=AmountOwed.Status.SATISFIED,
        )
        PaymentAttempt.objects.filter(pk=attempt.pk).update(billing_period=period)
        Subscription.objects.filter(pk=subscription.pk).update(
            state=Subscription.State.ACTIVE, current_period_start=start, current_period_end=end,
            active_agreement=agreement,
        )
    else:
        # Renewal success: the period was pre-created by BILL-WU-025 (not
        # built yet) — mark its amount-owed record satisfied and refresh
        # the subscription's cached current-period bounds.
        period = BillingPeriod.objects.get(pk=attempt.billing_period_id)
        AmountOwed.objects.filter(billing_period_id=period.pk).update(status=AmountOwed.Status.SATISFIED)
        Subscription.objects.filter(pk=subscription.pk).update(
            state=Subscription.State.ACTIVE, current_period_start=period.period_start,
            current_period_end=period.period_end,
        )


def apply(event_record):
    """Apply one verified, durably received `ProviderEvent` exactly once.
    Safe to call more than once for the same row (AC-BILL-021-2) and from
    more than one caller — the only state this ever changes is reached
    through the locked, re-checked path below."""
    merchant_order_id = (event_record.redacted_payload or {}).get("merchant_order_id", "")
    attempt = PaymentAttempt.objects.filter(merchant_order_id=merchant_order_id).first() if merchant_order_id else None
    if attempt is None:
        # Correlation (ADR-016 prerequisite 2): no match -> don't guess,
        # change no state, alert (recorded here as `last_error`; sending
        # an actual alert is out of scope — no notification channel
        # exists yet, BILL-DEC-06).
        _mark(event_record, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY,
              f"uncorrelated: no PaymentAttempt for merchant_order_id={merchant_order_id!r}")
        return

    kind = (event_record.event_type or "").lower()
    if kind in REFUND_LIKE_KINDS:
        _mark(event_record, ProviderEvent.ProcessingStatus.RECEIVED,
              "refund/void/reversal — stored only, not applied (BILL-WU-038 out of scope)")
        return

    # Consistency checks (never trust payload amounts over stored
    # expectations) — read unlocked: amount/currency are set once at
    # attempt creation and never updated afterward.
    payload = event_record.redacted_payload or {}
    expected_amount = payload.get("amount_minor_units")
    expected_currency = payload.get("currency")
    if expected_amount is not None and expected_amount != attempt.amount_minor_units:
        _mark(event_record, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY,
              "rejected-mismatch: amount_minor_units does not match the attempt's expected amount")
        return
    if expected_currency and expected_currency != attempt.currency:
        _mark(event_record, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY,
              "rejected-mismatch: currency does not match the attempt's expected currency")
        return

    with transaction.atomic():
        # Lock order: Subscription row -> PaymentAttempt row -> event row
        # (shared with BILL-WU-012/025/028, per this unit's own
        # preconditions).
        subscription = Subscription.objects.select_for_update().get(pk=attempt.subscription_id)
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        locked_event = ProviderEvent.objects.select_for_update().get(pk=event_record.pk)

        if locked_event.processing_status in _TERMINAL_PROCESSING_STATUSES:
            # AC-2: a second application of an already-resolved row
            # (bypassing receipt-time dedup) is a pure no-op.
            return

        if attempt.status not in PaymentAttempt.NON_TERMINAL_STATUSES:
            # Terminal precedence (AC-3): a terminal attempt is never
            # regressed by a late or contradictory event.
            _mark(locked_event, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY,
                  f"late/contradictory event for an already-terminal attempt (status={attempt.status!r})")
            return

        status = event_record.transaction_status
        if status in SUCCESS_LIKE_STATUSES:
            _apply_success(attempt, subscription, locked_event)
        elif status == "FAILURE":
            record_confirmed_failure(attempt)
        elif status == "PENDING":
            PaymentAttempt.objects.filter(pk=attempt.pk).update(status=PaymentAttempt.Status.PENDING)
        else:
            _mark(locked_event, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY,
                  f"unrecognized transaction_status {status!r}")
            return

        # Mark the event `processed` in the SAME transaction as the state
        # change (pattern: `process_ai_operations.py:109-120`) — a crash
        # leaves either both or neither (AC-7).
        ProviderEvent.objects.filter(pk=locked_event.pk).update(
            processing_status=ProviderEvent.ProcessingStatus.PROCESSED,
            attempts_count=locked_event.attempts_count + 1,
        )
        event_record.processing_status = ProviderEvent.ProcessingStatus.PROCESSED
