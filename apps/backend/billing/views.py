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
"""
from django.utils import timezone
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember, StandardPagination

from . import entitlements
from .models import PaymentAttempt, Plan, Subscription
from .serializers import PaymentHistoryRowSerializer, PlanSerializer, SubscriptionStatusSerializer

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


class PaymentHistoryView(generics.ListAPIView):
    """GET — the caller's environment's payment attempts, newest first,
    each annotated with its billing period's bounds. Paginated with the
    shared `StandardPagination` (`environments/tenancy.py`)."""

    permission_classes = IS_ENV_OWNER
    serializer_class = PaymentHistoryRowSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        return (
            PaymentAttempt.objects.filter(environment=self.request.environment)
            .select_related("billing_period")
            .order_by("-created_at")
        )
