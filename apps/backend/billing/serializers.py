"""
BILL-WU-031 — PROPOSED read-only serializers for the billing API namespace.

NODE-WireAPI (`../decisions.md`) defers the serialized schema/endpoint
catalog to the API-documentation stage; this is a working proposal handed
off to BILL-WU-032, not a finalized contract.

None of these ever serializes a billing model directly with a plain
`ModelSerializer` over every field: fields are listed explicitly so a
later model addition (e.g. a token/agreement FK on `Subscription`) can
never leak into a response just by existing (AC-BILL-031-3).
"""
from rest_framework import serializers

from .models import PaymentAttempt, Plan


class PlanSerializer(serializers.ModelSerializer):
    class Meta:
        model = Plan
        fields = ["key", "name", "price_minor_units", "currency", "max_students"]


class CheckoutRequestSerializer(serializers.Serializer):
    """BILL-WU-019 — the body carries only a plan identifier (this unit's
    own "Expected outcome"). Any other field sent (`amount`, `currency`,
    `status`, `environment_id`, ...) is simply not a declared field, so DRF
    never reads it into `validated_data` — AC-BILL-019-2."""

    plan_key = serializers.ChoiceField(choices=Plan.Key.choices)


class CheckoutResponseSerializer(serializers.Serializer):
    session_url = serializers.CharField()
    attempt_id = serializers.IntegerField()


class CheckoutStatusSerializer(serializers.Serializer):
    """The redirect-return page's display-only payload (ADR-016) — current
    server-side status, nothing the query string said."""

    attempt_id = serializers.IntegerField(allow_null=True)
    status = serializers.CharField(allow_null=True)


class EntitlementSummarySerializer(serializers.Serializer):
    """Mirrors `billing.entitlements.EntitlementDecision` — never the ORM
    model, since this is a computed decision, not a stored row."""

    access_granted = serializers.BooleanField()
    basis = serializers.CharField()
    reason_code = serializers.CharField()
    capabilities = serializers.ListField(child=serializers.CharField())
    student_cap = serializers.IntegerField(allow_null=True)


class SubscriptionStatusSerializer(serializers.Serializer):
    """Hand-assembled view combining a few `Subscription` fields with the
    BILL-WU-010 entitlement summary. No internal ids (`Subscription.pk`,
    `environment_id`, `active_agreement_id`) are included — the client
    needs the plan key and the dates, not row ids."""

    plan_key = serializers.CharField(allow_null=True)
    trial_end = serializers.DateTimeField(allow_null=True)
    current_period_end = serializers.DateTimeField(allow_null=True)
    cancel_at_period_end = serializers.BooleanField()
    entitlement = EntitlementSummarySerializer()


class PaymentHistoryRowSerializer(serializers.ModelSerializer):
    """One `PaymentAttempt`, annotated with its `BillingPeriod`'s bounds.
    Deliberately excludes `merchant_order_id`, `provider_transaction_id`
    and `provider_order_id` — Madar/provider correlation identifiers the
    teacher-facing history view has no documented need for, and which
    this unit's own security considerations ask to keep out (AC-3)."""

    period_start = serializers.SerializerMethodField()
    period_end = serializers.SerializerMethodField()

    class Meta:
        model = PaymentAttempt
        fields = ["id", "status", "amount_minor_units", "currency", "created_at", "period_start", "period_end"]

    def get_period_start(self, obj):
        return obj.billing_period.period_start if obj.billing_period_id else None

    def get_period_end(self, obj):
        return obj.billing_period.period_end if obj.billing_period_id else None
