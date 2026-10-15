"""
Billing's private persistence (BILL-WU-008; DAT-5 candidate logical concepts;
ADR-014 module ownership; ADR-016/017 payment-event safety).

This module owns the Teacher-to-Madar commercial relationship: plans,
subscriptions, billing periods, amounts owed, payment attempts, recurring
(Kashier) agreement references, and verified provider-event records. It is
strictly separate from `financials`, which tracks the unrelated Student-to-
Teacher educational fee (`financials.MonthlyPayment`) and is never read from
or written to here (BND-1/BND-4; see `financials/models.py`'s own docstring
for that boundary).

Physical names below are this implementer's choice; the DAT-5 *logical*
concepts and their mandatory integrity guarantees are not. Nothing here
decides a subscription-state vocabulary as System/Backend doctrine: ADR-017
leaves the exact state names open, so the five below (TRIAL/ACTIVE/
PAST_DUE/CANCELED/EXPIRED) are a reviewed PROPOSAL for this PR, not an
accepted decision — a later Work Unit may rename them without this being a
"redefinition" of anything System-level.

No model here stores a PAN, CVV, or any other full card number — only
opaque provider-issued token/agreement identifiers (ADR-015). No model here
is a FK to, or from, `financials`. No model here imports `config.months`:
`BillingPeriod` is 30 *elapsed* days, never a calendar month (BILL-WU-024).

Deliberate cascade choice (recorded per this unit's own instruction): a
`Subscription` and its `BillingPeriod` children use TenantOwnedModel's
CASCADE (deleting the Environment deletes its billing state — consistent
with every other tenant-scoped model in this codebase). `PaymentAttempt`
and `ProviderEvent`, however, are financial/audit records that must never
silently disappear just because an Environment row is later removed, so
they use PROTECT: an attempt to delete an Environment that still has
payment attempts raises `ProtectedError` rather than erasing the money
trail. This mirrors "data is never destroyed under access-not-granted"
(see this unit's own "Data-integrity & security considerations").
"""
from django.db import models
from django.db.models import Q

from environments.models import Environment
from environments.tenancy import TenantOwnedModel


class Plan(models.Model):
    """Global plan catalog entry. Not teacher-scoped — every Environment
    reads the same rows. Plan *data* (the three approved rows) is seeded by
    BILL-WU-009, not here; this is the table shape only."""

    class Key(models.TextChoices):
        PLAN_1 = "plan_1", "Plan 1"
        PLAN_2 = "plan_2", "Plan 2"
        PLAN_3 = "plan_3", "Plan 3"

    key = models.CharField(max_length=20, choices=Key.choices, unique=True)
    name = models.CharField(max_length=100)
    # Integer minor units (piastres) to avoid float/Decimal rounding
    # ambiguity in money comparisons. 1000.00 EGP == 100000 piastres.
    price_minor_units = models.IntegerField()
    currency = models.CharField(max_length=3, default="EGP")
    # null = no plan-level numerical student cap (Plan 3). Never 0.
    max_students = models.PositiveIntegerField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(price_minor_units__gte=0), name="plan_price_non_negative"),
        ]

    def __str__(self):
        return self.key


class RecurringAgreement(TenantOwnedModel):
    """An opaque Kashier recurring-payment agreement/card-token reference
    (ADR-015). `card_token` and `kashier_agreement_id` are provider-issued
    opaque strings only — never a PAN, CVV, or any other cardholder data.
    `mode` is recorded so a test-mode token can never be charged live."""

    class Mode(models.TextChoices):
        TEST = "test", "Test"
        LIVE = "live", "Live"

    subscription = models.ForeignKey(
        "billing.Subscription", on_delete=models.PROTECT, related_name="agreements"
    )
    card_token = models.CharField(max_length=255)
    kashier_agreement_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    mode = models.CharField(max_length=4, choices=Mode.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"RecurringAgreement#{self.pk} [{self.mode}]"


class Subscription(TenantOwnedModel):
    """At most one per Environment (ADR-013/INV-9; enforced below via
    OneToOneField, overriding TenantOwnedModel's plain FK). Holds the
    commercial state and the active recurring agreement, if any."""

    class State(models.TextChoices):
        # PROPOSED names (see module docstring) — not an ADR-017 decision.
        TRIAL = "trial", "Trial"
        ACTIVE = "active", "Active"
        PAST_DUE = "past_due", "Past due (grace period)"
        CANCELED = "canceled", "Canceled (runs to period end)"
        EXPIRED = "expired", "Expired"

    environment = models.OneToOneField(
        Environment, on_delete=models.CASCADE, related_name="billing_subscription"
    )
    plan = models.ForeignKey(Plan, on_delete=models.PROTECT, null=True, blank=True, related_name="+")
    state = models.CharField(max_length=10, choices=State.choices, default=State.TRIAL)

    trial_started_at = models.DateTimeField(null=True, blank=True)
    trial_ends_at = models.DateTimeField(null=True, blank=True)

    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)

    cancel_at_period_end = models.BooleanField(default=False)
    active_agreement = models.ForeignKey(
        RecurringAgreement, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Subscription#{self.pk} env={self.environment_id} [{self.state}]"


class BillingPeriod(TenantOwnedModel):
    """A [start, end) window belonging to a Subscription. `end` is always
    `start + 30 elapsed days` (BILL-WU-024 computes this; this model does
    not derive it) — never a calendar month, and `config.months` is never
    imported here."""

    subscription = models.ForeignKey(Subscription, on_delete=models.CASCADE, related_name="periods")
    period_start = models.DateTimeField()
    period_end = models.DateTimeField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["subscription", "period_start"], name="unique_billingperiod_subscription_start"
            ),
        ]

    def __str__(self):
        return f"BillingPeriod#{self.pk} sub={self.subscription_id} [{self.period_start:%Y-%m-%d}]"


class AmountOwed(TenantOwnedModel):
    """The internal amount-owed record for one BillingPeriod ("invoice
    where required" per DAT-5). No tax or receipt fields — invoice/tax
    requirements are open (BILL-WU-040). Amount and currency are always
    copied from the Plan at creation time by the service layer, never
    client-supplied (mirrors `financials/serializers.py`'s server-authority
    pattern for `MonthlyPayment.amount`)."""

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        SATISFIED = "satisfied", "Satisfied"
        VOID = "void", "Void"

    billing_period = models.OneToOneField(BillingPeriod, on_delete=models.CASCADE, related_name="amount_owed")
    amount_minor_units = models.IntegerField()
    currency = models.CharField(max_length=3, default="EGP")
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.OPEN)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount_minor_units__gte=0), name="amount_owed_non_negative"),
        ]

    def __str__(self):
        return f"AmountOwed#{self.pk} period={self.billing_period_id} [{self.status}]"


class PaymentAttempt(TenantOwnedModel):
    """Belongs to a Subscription, and to a BillingPeriod for renewals (null
    for an initial-checkout attempt that precedes any period). PROTECTed
    (see module docstring) — never cascade-deleted with the Environment.

    `merchant_order_id` is Madar-generated, unique, and non-guessable: it is
    the `merchantOrderId` correlation key sent to Kashier. At most one
    non-terminal attempt may exist per BillingPeriod at a time (the
    double-charge guard for renewals) — terminal attempts never block a
    later retry.
    """

    class Status(models.TextChoices):
        INITIATED = "initiated", "Initiated"
        PENDING = "pending", "Pending"
        SUCCEEDED = "succeeded", "Succeeded"
        FAILED = "failed", "Failed"
        # A transport timeout or other ambiguous outcome. Never silently
        # requeued as pending (ai-execution-guidance directive 12) — stays
        # UNKNOWN until reconciliation resolves it one way or the other.
        UNKNOWN = "unknown", "Unknown (needs reconciliation)"

    # Plain strings, not `Status.X` — a nested `Meta` class body cannot see
    # names bound in the enclosing class body, so this is referenced from
    # Meta.constraints below and must stay a literal tuple of the same
    # values as Status.{INITIATED,PENDING,UNKNOWN}.
    NON_TERMINAL_STATUSES = ("initiated", "pending", "unknown")

    # Overrides TenantOwnedModel's CASCADE: a financial record must not
    # silently disappear just because the Environment row is later
    # removed (see module docstring).
    environment = models.ForeignKey(Environment, on_delete=models.PROTECT, related_name="+")
    subscription = models.ForeignKey(Subscription, on_delete=models.PROTECT, related_name="payment_attempts")
    billing_period = models.ForeignKey(
        BillingPeriod, on_delete=models.PROTECT, null=True, blank=True, related_name="payment_attempts"
    )

    merchant_order_id = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=9, choices=Status.choices, default=Status.INITIATED)

    amount_minor_units = models.IntegerField()
    currency = models.CharField(max_length=3, default="EGP")

    provider_transaction_id = models.CharField(max_length=255, null=True, blank=True, unique=True)
    provider_order_id = models.CharField(max_length=255, null=True, blank=True, unique=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(amount_minor_units__gte=0), name="payment_attempt_amount_non_negative"),
            models.UniqueConstraint(
                fields=["billing_period"],
                condition=Q(status__in=["initiated", "pending", "unknown"]),
                name="unique_non_terminal_attempt_per_billing_period",
            ),
        ]

    def __str__(self):
        return f"PaymentAttempt#{self.pk} [{self.status}] order={self.merchant_order_id}"


class ProviderEvent(models.Model):
    """Every **verified** inbound Kashier event (ADR-016). Global, not
    TenantOwnedModel: an event is correlated to an Environment only after
    signature verification and lookup via `merchant_order_id`/provider ids
    (BILL-WU-020 owns that correlation logic — this model only holds the
    nullable `environment` the correlation step fills in).

    This is entirely separate from `ai.AIOperation.idempotency_key`
    (ADR-017): that mechanism dedups a *client's own retried request*; this
    one dedups a *provider's possibly-repeated delivery* of the same event,
    using a key derived from provider identifiers, not anything a client
    ever sends.

    Does not store the raw webhook body: `data.card.cardInfo` and similar
    fields may carry a cardholder name and a masked card number, so only a
    `redacted_payload` (already stripped of card-shaped fields) is kept
    here. Full redaction logic is BILL-WU-035's job; this schema is shaped
    so a raw, unredacted body is never a field that exists to misuse.
    """

    class ProcessingStatus(models.TextChoices):
        RECEIVED = "received", "Received"
        PROCESSED = "processed", "Processed"
        FAILED_TO_APPLY = "failed_to_apply", "Failed to apply"
        IGNORED_DUPLICATE = "ignored_duplicate", "Ignored (duplicate)"

    class Mode(models.TextChoices):
        TEST = "test", "Test"
        LIVE = "live", "Live"

    # Derived by BILL-WU-020 from provider identifiers (at minimum
    # transactionId + status + event per that unit's composition rule).
    dedup_key = models.CharField(max_length=255, unique=True)

    environment = models.ForeignKey(
        Environment, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )

    mode = models.CharField(max_length=4, choices=Mode.choices)
    event_type = models.CharField(max_length=64)
    transaction_status = models.CharField(max_length=32, blank=True)
    provider_transaction_id = models.CharField(max_length=255, blank=True)
    provider_order_id = models.CharField(max_length=255, blank=True)

    signature_valid = models.BooleanField()
    redacted_payload = models.JSONField(default=dict, blank=True)

    received_at = models.DateTimeField(auto_now_add=True)
    processing_status = models.CharField(
        max_length=20, choices=ProcessingStatus.choices, default=ProcessingStatus.RECEIVED
    )
    attempts_count = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True)

    def __str__(self):
        return f"ProviderEvent#{self.pk} [{self.processing_status}] {self.event_type}"
