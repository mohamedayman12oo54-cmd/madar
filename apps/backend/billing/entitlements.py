"""
Billing's entitlement-policy contract (BILL-WU-010; ADR-018).

`decide(environment, *, now=None)` is the single, explicit, Billing-owned
answer to "does this Environment's Teacher currently have access, and to
which plan-gated capabilities and student cap?" It is a pure, side-effect-
free read: no writes, no caching (none is introduced here — if caching is
added later it must be invalidated on every billing state transition,
per this unit's own exclusions). `now` is injected so callers/tests are
deterministic; production code passes `timezone.now()` (the default).

This contract is consumed by other boundaries (a permission class run
*after* `IsEnvironmentMember` resolves tenant context, per ADR-018) — it is
**not** itself an enforcement point (BILL-WU-011/012/013 are), and it must
**never** be folded into `accounts/authentication.py`'s
`MadarJWTAuthentication.get_user()` merely because that hook runs on every
request (ADR-018's whole point). That file does not import this module —
see AC-BILL-010-7 and the static test enforcing it.

Naming reconciliation (recorded, not silently resolved): this unit's own
"Expected outcome" paragraph lists a basis value `paid-past-due-within-
unbounded-grace`, while its "Derivation rules" paragraph gives the literal
field value `payment_failed_pending_policy` for the same state (one failed
renewal, access not yet terminated, no numeric grace bound exists because
BILL-DEC-05 is still open — hence "unbounded"). This module uses the
Derivation Rules' literal value, `Basis.PAYMENT_FAILED_PENDING_POLICY`, as
the actual field value; the other phrase is this same state's prose
description, not a second basis.

Open items this contract deliberately does NOT resolve (preserved, not
defaulted):
- BILL-DEC-02: what a consumer does with "access not granted" for
  general (non-plan-gated) capability is decided in BILL-WU-013, not here.
  This module only reports `access_granted` and `reason_code`.
- BILL-DEC-05: the grace period after a failed renewal has no numeric
  duration. `Basis.PAYMENT_FAILED_PENDING_POLICY` is reported with
  `access_granted=True` and no invented expiry — `period_end` on that
  result is simply the already-elapsed BillingPeriod's own known end, not
  a new deadline.
"""
import dataclasses
from typing import Optional

from django.utils import timezone
from rest_framework import exceptions

from . import capabilities
from .models import PaymentAttempt, Subscription

TRIAL_DAYS = 16


class StudentCapReached(exceptions.PermissionDenied):
    """BILL-WU-012 — a stable, machine-readable rejection for "this
    Environment's counted-student set is already at its plan's cap."
    `Basis`/cap NUMBERS are commercial-model's decided values via
    `decide()`; the counted SET is academics' own tracked open item
    (`academics.access.count_for_cap`'s docstring) — this exception
    carries neither, by design, so it never needs to change when that
    open item resolves."""

    default_detail = "تم الوصول للحد الأقصى لعدد الطلاب المسموح به في باقتك الحالية."
    default_code = "student_cap_reached"


class Basis:
    TRIAL = "trial"
    PAID_ACTIVE = "paid_active"
    CANCELLED_BUT_PAID_THROUGH = "cancelled_but_paid_through"
    PAYMENT_FAILED_PENDING_POLICY = "payment_failed_pending_policy"
    NONE = "none"


class ReasonCode:
    TRIAL_ACTIVE = "trial_active"
    PAID_ACTIVE = "paid_active"
    CANCELLED_BUT_PAID_THROUGH = "cancelled_but_paid_through"
    PAYMENT_FAILED_PENDING_POLICY = "payment_failed_pending_policy"
    TRIAL_EXPIRED = "trial_expired"
    PERIOD_ENDED = "period_ended"
    NO_SUBSCRIPTION = "no_subscription"


# Always allowed regardless of `access_granted` (ADR-018; commercial-model
# §Access-not-granted): authentication, resolving/managing billing itself,
# and reviewing/exporting one's own data. Enforcement points consult
# `EntitlementDecision.permits(category)` rather than re-deriving this list,
# so a category can never be accidentally gated by forgetting it exists.
ALWAYS_PERMITTED_CATEGORIES = frozenset({"authentication", "billing_resolution", "data_export"})


@dataclasses.dataclass(frozen=True)
class EntitlementDecision:
    access_granted: bool
    basis: str
    capabilities: frozenset
    student_cap: Optional[int]
    period_end: Optional["datetime.datetime"]
    reason_code: str

    def permits(self, category):
        if category in ALWAYS_PERMITTED_CATEGORIES:
            return True
        return self.access_granted


def _no_access(reason_code):
    return EntitlementDecision(
        access_granted=False, basis=Basis.NONE, capabilities=frozenset(),
        student_cap=None, period_end=None, reason_code=reason_code,
    )


def decide(environment, *, now=None):
    now = now or timezone.now()

    try:
        subscription = Subscription.objects.select_related("plan").get(environment=environment)
    except Subscription.DoesNotExist:
        return _no_access(ReasonCode.NO_SUBSCRIPTION)

    # Trial: granted iff trial_start <= now < trial_start + 16 elapsed days
    # (server instants; never calendar-month arithmetic).
    if subscription.trial_started_at is not None:
        trial_end = subscription.trial_started_at + timezone.timedelta(days=TRIAL_DAYS)
        if subscription.trial_started_at <= now < trial_end:
            return EntitlementDecision(
                access_granted=True, basis=Basis.TRIAL, capabilities=capabilities.TRIAL_CAPABILITIES,
                student_cap=capabilities.TRIAL_STUDENT_CAP, period_end=trial_end,
                reason_code=ReasonCode.TRIAL_ACTIVE,
            )

    # Paid: granted iff a succeeded payment covers a BillingPeriod with
    # start <= now < end. cancel_at_period_end does not change whether the
    # CURRENT period is granted — it only prevents a future period from
    # being created (commercial-model §Cancellation) — so it only changes
    # which basis/reason_code is reported, not access_granted itself.
    current_period = (
        subscription.periods.filter(period_start__lte=now, period_end__gt=now)
        .order_by("-period_start").first()
    )
    if current_period is not None and subscription.plan_id:
        covered = PaymentAttempt.objects.filter(
            billing_period=current_period, status=PaymentAttempt.Status.SUCCEEDED
        ).exists()
        if covered:
            plan_capabilities = capabilities.capabilities_for_plan(subscription.plan.key)
            if subscription.cancel_at_period_end:
                basis, reason_code = Basis.CANCELLED_BUT_PAID_THROUGH, ReasonCode.CANCELLED_BUT_PAID_THROUGH
            else:
                basis, reason_code = Basis.PAID_ACTIVE, ReasonCode.PAID_ACTIVE
            return EntitlementDecision(
                access_granted=True, basis=basis, capabilities=plan_capabilities,
                student_cap=subscription.plan.max_students, period_end=current_period.period_end,
                reason_code=reason_code,
            )

    # A single failed renewal does not terminate access (commercial-model
    # §Failed renewal). Until BILL-DEC-05 sets retry/grace numbers, a
    # BillingPeriod that has ended with a failed (not succeeded) attempt
    # stays granted, flagged, with no invented expiry.
    last_ended_period = (
        subscription.periods.filter(period_end__lte=now).order_by("-period_end").first()
    )
    if last_ended_period is not None and subscription.plan_id:
        attempts_for_period = PaymentAttempt.objects.filter(billing_period=last_ended_period)
        has_failed = attempts_for_period.filter(status=PaymentAttempt.Status.FAILED).exists()
        has_succeeded = attempts_for_period.filter(status=PaymentAttempt.Status.SUCCEEDED).exists()
        if has_failed and not has_succeeded:
            return EntitlementDecision(
                access_granted=True, basis=Basis.PAYMENT_FAILED_PENDING_POLICY,
                capabilities=capabilities.capabilities_for_plan(subscription.plan.key),
                student_cap=subscription.plan.max_students, period_end=last_ended_period.period_end,
                reason_code=ReasonCode.PAYMENT_FAILED_PENDING_POLICY,
            )

    # Not granted.
    if subscription.trial_started_at is not None and now >= subscription.trial_started_at + timezone.timedelta(
        days=TRIAL_DAYS
    ):
        return _no_access(ReasonCode.TRIAL_EXPIRED)
    return _no_access(ReasonCode.PERIOD_ENDED)


def student_cap_locked(environment, *, now=None):
    """BILL-WU-012 — the same `student_cap` `decide()` would report, but
    read with the Environment's Subscription row locked
    (`select_for_update()`) first — this unit's own required race-safety:
    "lock the Environment's Subscription row inside the same
    `transaction.atomic()` as the insert, so two concurrent adds cannot
    both pass at cap − 1." MUST be called from inside the caller's own
    `transaction.atomic()` block — `select_for_update()` requires an open
    transaction and raises `TransactionManagementError` otherwise; this
    function deliberately does not open one itself, so the lock is held
    for exactly as long as the CALLER's transaction is (through the
    caller's own insert), not just for this read.

    Billing owns the Subscription row (BND-1) — academics never queries
    `billing.models.Subscription` directly, only this function, even
    though the lock it takes is what actually makes academics' own insert
    race-safe."""
    try:
        Subscription.objects.select_for_update().get(environment=environment)
    except Subscription.DoesNotExist:
        pass
    return decide(environment, now=now).student_cap
