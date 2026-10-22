"""
BILL-WU-031 — Teacher billing API namespace (`/api/v1/billing/`). PROPOSED
read surface per NODE-WireAPI (`../decisions.md`): the serialized schema,
HTTP status choices and endpoint catalog are not finalized here — they are
handed off to BILL-WU-032. This unit only delivers a working, tenant-safe
read surface at AL-4's indicative shape.

Deliberately NOT gated by `entitlements.decide(...).access_granted`:
billing resolution is one of the always-permitted categories
(`billing.entitlements.ALWAYS_PERMITTED_CATEGORIES`) — these endpoints must
stay reachable even when access is not granted (commercial-model
§Access-not-granted; AL-4), which is exactly what AC-BILL-031-4 tests.

Checkout (BILL-WU-019), cancellation (BILL-WU-028) and the webhook
(BILL-WU-020) endpoints mount into this same `billing.urls` namespace in
later units — explicitly out of scope here (this unit's own exclusions).

`CancelSubscriptionView` below is BILL-WU-028, not this unit — it is
added later, into this same file/namespace, per that unit's own
"Implementation surfaces".
"""
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from accounts.throttles import BillingCancelRateThrottle, BillingCheckoutRateThrottle, BillingStatusRateThrottle
from environments.tenancy import IsEnvironmentMember, StandardPagination

from . import entitlements
from .models import PaymentAttempt, Plan, Subscription
from .serializers import (
    CancelResponseSerializer,
    CheckoutRequestSerializer,
    CheckoutResponseSerializer,
    CheckoutStatusSerializer,
    PaymentHistoryRowSerializer,
    PlanSerializer,
    SubscriptionStatusSerializer,
)
from .services import CancelError, CheckoutError, cancel_subscription, get_checkout_status, start_checkout

# Every environment-scoped billing endpoint requires the caller to be the
# OWNER member of their own environment (header-resolved, never trusted
# from the body) — the same pattern `financials/views.py` uses.
IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]


class PlanListView(generics.ListAPIView):
    """GET — the global plan catalog. Any authenticated teacher; no
    environment header is consulted (this is not tenant-scoped data)."""

    permission_classes = [IsTeacher]
    serializer_class = PlanSerializer
    pagination_class = None

    def get_queryset(self):
        return Plan.objects.filter(is_active=True).order_by("key")


class SubscriptionStatusView(APIView):
    """GET — the caller's environment's subscription/trial status plus its
    BILL-WU-010 entitlement summary."""
    throttle_classes = [BillingStatusRateThrottle]

    permission_classes = IS_ENV_OWNER

    def get(self, request):
        environment = request.environment
        decision = entitlements.decide(environment)
        try:
            subscription = Subscription.objects.select_related("plan").get(environment=environment)
        except Subscription.DoesNotExist:
            subscription = None

        trial_end = None
        if subscription is not None and subscription.trial_started_at is not None:
            trial_end = subscription.trial_started_at + timezone.timedelta(days=entitlements.TRIAL_DAYS)

        data = {
            "plan_key": subscription.plan.key if subscription is not None and subscription.plan_id else None,
            "trial_end": trial_end,
            "current_period_end": subscription.current_period_end if subscription is not None else None,
            "cancel_at_period_end": bool(subscription is not None and subscription.cancel_at_period_end),
            "pending_checkout": _pending_checkout(environment),
            "entitlement": {
                "access_granted": decision.access_granted,
                "basis": decision.basis,
                "reason_code": decision.reason_code,
                "capabilities": sorted(decision.capabilities),
                "student_cap": decision.student_cap,
            },
        }
        serializer = SubscriptionStatusSerializer(data)
        return Response(serializer.data)


def _pending_checkout(environment):
    attempt = (
        PaymentAttempt.objects.select_related("plan")
        .filter(environment=environment, billing_period__isnull=True,
                status__in=[PaymentAttempt.Status.INITIATED, PaymentAttempt.Status.PENDING, PaymentAttempt.Status.UNKNOWN])
        .order_by("-created_at").first()
    )
    if attempt is None:
        return None
    return {"attempt_id": attempt.pk, "status": attempt.status, "plan_key": attempt.plan.key if attempt.plan_id else None}


def _return_url_for(attempt):
    """Where the teacher's browser lands after the hosted page: a FRONTEND route (display only —
    a redirect is never proof of payment). `attempt_id` is the only thing the page reads, and the
    server re-checks that the attempt belongs to the caller's environment."""
    from django.conf import settings

    base = settings.BILLING_CHECKOUT_RETURN_URL or "http://localhost:5173/app/billing"
    return f"{base}{'&' if '?' in base else '?'}attempt_id={attempt.pk}"


class CheckoutView(APIView):
    """POST — start (or resume) Kashier's hosted recurring-setup checkout
    for one plan (BILL-WU-019). Allowed in EVERY access state — billing
    resolution is one of `entitlements.ALWAYS_PERMITTED_CATEGORIES`, so
    this is deliberately not gated by `entitlements.decide(...)`
    (AC-BILL-019-6)."""
    throttle_classes = [BillingCheckoutRateThrottle]

    permission_classes = IS_ENV_OWNER

    def post(self, request):
        serializer = CheckoutRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            attempt, session_url = start_checkout(
                request.environment, serializer.validated_data["plan_key"], _return_url_for
            )
        except CheckoutError as exc:
            http_status = (
                status.HTTP_409_CONFLICT if exc.code in ("paid_period_active", "checkout_in_progress")
                else status.HTTP_503_SERVICE_UNAVAILABLE if exc.code == "provider_unavailable"
                else status.HTTP_400_BAD_REQUEST
            )
            return Response({"detail": exc.detail, "code": exc.code}, status=http_status)

        response = CheckoutResponseSerializer({"session_url": session_url, "attempt_id": attempt.id})
        return Response(response.data, status=status.HTTP_201_CREATED)


class CheckoutReturnView(APIView):
    """GET — the redirect-return landing page. **Display only** (ADR-016):
    whatever the query string claims (including anything that looks like
    "success"), this view never writes to Subscription, PaymentAttempt or
    entitlement state — it only reports the attempt's current server-side
    status (AC-BILL-019-3)."""
    throttle_classes = [BillingStatusRateThrottle]

    permission_classes = IS_ENV_OWNER

    def get(self, request):
        attempt = get_checkout_status(request.environment, request.query_params.get("attempt_id"))
        data = {"attempt_id": attempt.id if attempt else None, "status": attempt.status if attempt else None}
        serializer = CheckoutStatusSerializer(data)
        return Response(serializer.data)


class CancelSubscriptionView(APIView):
    """POST — BILL-WU-028. Always permitted for the owner (commercial-model
    §Cancellation): not gated by `entitlements.decide(...)` for the same
    reason `CheckoutView` isn't (billing resolution is always-permitted).
    Idempotent; never deletes data or issues a refund (this unit's own
    exclusions, AC-BILL-028-5)."""
    throttle_classes = [BillingCancelRateThrottle]

    permission_classes = IS_ENV_OWNER

    def post(self, request):
        try:
            result = cancel_subscription(request.environment)
        except CancelError as exc:
            return Response({"detail": exc.detail, "code": exc.code}, status=status.HTTP_404_NOT_FOUND)

        serializer = CancelResponseSerializer(
            {
                "cancel_at_period_end": result.cancel_at_period_end,
                "renewal_already_in_progress": result.renewal_already_in_progress,
                "renewal_attempt_status": result.renewal_attempt_status,
            }
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class PaymentHistoryView(generics.ListAPIView):
    """GET — the caller's environment's payment attempts, newest first,
    each annotated with its billing period's bounds. Paginated with the
    shared `StandardPagination` (`environments/tenancy.py`)."""
    throttle_classes = [BillingStatusRateThrottle]

    permission_classes = IS_ENV_OWNER
    serializer_class = PaymentHistoryRowSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        return (
            PaymentAttempt.objects.filter(environment=self.request.environment)
            .select_related("billing_period")
            .order_by("-created_at")
        )
