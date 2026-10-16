"""
BILL-WU-031 — integration tests for the teacher billing API namespace.

Uses `TenantTestCase` (`environments/tenancy_testing.py`) — the shared
two-teacher cross-tenant fixture every tenant-scoped endpoint in this
codebase is tested with.
"""
from django.utils import timezone

from environments.tenancy_testing import TenantTestCase

from .models import PaymentAttempt, Plan, RecurringAgreement, Subscription


def _make_subscription(environment, **extra):
    return Subscription.objects.create(environment=environment, **extra)


class PlanListEndpointTests(TenantTestCase):
    """AC-BILL-031-1 (plans) and AC-BILL-031-2 (students refused)."""

    def test_an_authenticated_teacher_sees_the_three_plans(self):
        r = self.client_a.get("/api/v1/billing/plans/")
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(len(body), 3)
        keys = {row["key"] for row in body}
        self.assertEqual(keys, {Plan.Key.PLAN_1, Plan.Key.PLAN_2, Plan.Key.PLAN_3})
        plan_1 = next(row for row in body if row["key"] == Plan.Key.PLAN_1)
        self.assertEqual(plan_1["price_minor_units"], 100000)
        self.assertEqual(plan_1["max_students"], 400)

    def test_a_student_is_refused(self):
        student = self.make_student_in(self.env_a, "201020000099")
        from rest_framework.test import APIClient

        # Students authenticate via a separate claim/OTP flow; rather than
        # reproduce that whole flow, force-authenticate directly to isolate
        # what this test actually checks: role-based refusal of this
        # namespace, not the student login flow itself.
        client = APIClient()
        client.force_authenticate(user=student)
        r = client.get("/api/v1/billing/plans/")
        self.assertIn(r.status_code, (401, 403))

    def test_anonymous_is_refused(self):
        from rest_framework.test import APIClient

        r = APIClient().get("/api/v1/billing/plans/")
        self.assertEqual(r.status_code, 401)


class SubscriptionStatusEndpointTests(TenantTestCase):
    """AC-BILL-031-1, AC-BILL-031-2, AC-BILL-031-3."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_2)
        self.subscription = _make_subscription(
            self.env_a, plan=self.plan, cancel_at_period_end=False,
            current_period_end=timezone.now() + timezone.timedelta(days=10),
        )
        self.agreement = RecurringAgreement.objects.create(
            environment=self.env_a, subscription=self.subscription,
            card_token="super-secret-opaque-token", kashier_agreement_id="agr_shouldnotleak",
            mode=RecurringAgreement.Mode.TEST,
        )
        self.subscription.active_agreement = self.agreement
        self.subscription.save(update_fields=["active_agreement"])

    def test_the_owner_sees_their_own_subscription_status(self):
        r = self.client_a.get("/api/v1/billing/subscription/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["plan_key"], Plan.Key.PLAN_2)
        self.assertIn("entitlement", body)
        self.assertIn("access_granted", body["entitlement"])

    def test_cross_tenant_read_is_denied(self):
        self.assert_cross_tenant_denied("get", "/api/v1/billing/subscription/")

    def test_a_non_owner_member_of_the_same_environment_is_refused(self):
        student = self.make_student_in(self.env_a, "201020000098")
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=student)
        r = client.get("/api/v1/billing/subscription/", **self.with_env(self.env_a.id))
        self.assertIn(r.status_code, (401, 403))

    def test_response_never_contains_the_card_token_or_agreement_id(self):
        r = self.client_a.get("/api/v1/billing/subscription/", **self.with_env(self.env_a.id))
        raw = r.content.decode()
        for leaked in ("super-secret-opaque-token", "agr_shouldnotleak", "card_token", "kashier_agreement_id"):
            self.assertNotIn(leaked, raw, f"leaked {leaked!r}")

    def test_reachable_when_no_subscription_row_exists_yet(self):
        """A teacher who has never had a Subscription row created (BILL-
        WU-014 hasn't wired trial-start into signup yet) must still get a
        200 with a 'no_subscription' entitlement, never a 404/500.
        `env_b` never had a Subscription row created for it at all — no
        setup needed beyond the base TenantTestCase fixture."""
        r = self.client_b.get("/api/v1/billing/subscription/", **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertIsNone(body["plan_key"])
        self.assertFalse(body["entitlement"]["access_granted"])
        self.assertEqual(body["entitlement"]["reason_code"], "no_subscription")


class SubscriptionStatusExpiredTrialTests(TenantTestCase):
    """AC-BILL-031-4: reachable even when access is not granted."""

    def test_reachable_for_an_environment_whose_trial_has_expired(self):
        long_ago = timezone.now() - timezone.timedelta(days=100)
        _make_subscription(self.env_a, trial_started_at=long_ago)

        r = self.client_a.get("/api/v1/billing/subscription/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertFalse(r.json()["entitlement"]["access_granted"])
        self.assertEqual(r.json()["entitlement"]["reason_code"], "trial_expired")

    def test_history_is_also_reachable_for_an_expired_trial(self):
        long_ago = timezone.now() - timezone.timedelta(days=100)
        _make_subscription(self.env_a, trial_started_at=long_ago)

        r = self.client_a.get("/api/v1/billing/history/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)

    def test_plans_catalog_is_reachable_regardless_of_any_environments_state(self):
        r = self.client_a.get("/api/v1/billing/plans/")
        self.assertEqual(r.status_code, 200, r.content)


class CancelSubscriptionEndpointTests(TenantTestCase):
    """BILL-WU-028 — AC-BILL-028-5 (no refund/deletion, via the HTTP
    surface) and AC-BILL-028-6 (non-owner/cross-tenant refused). The
    race-safety ACs (2-4) and the frozen-clock AC (1) are exercised at the
    service layer directly in `test_cancel.py`, which needs real
    (non test-wrapped) transactions `TenantTestCase` doesn't give."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.subscription = _make_subscription(
            self.env_a, plan=self.plan, state=Subscription.State.ACTIVE, cancel_at_period_end=False,
            current_period_start=timezone.now() - timezone.timedelta(days=5),
            current_period_end=timezone.now() + timezone.timedelta(days=25),
        )

    def test_the_owner_can_cancel_and_the_response_reflects_the_flag(self):
        r = self.client_a.post("/api/v1/billing/subscription/cancel/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertTrue(body["cancel_at_period_end"])
        self.assertFalse(body["renewal_already_in_progress"])
        self.subscription.refresh_from_db()
        self.assertTrue(self.subscription.cancel_at_period_end)

    def test_a_repeat_cancel_call_is_idempotent(self):
        self.client_a.post("/api/v1/billing/subscription/cancel/", **self.with_env(self.env_a.id))
        r = self.client_a.post("/api/v1/billing/subscription/cancel/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["cancel_at_period_end"])

    def test_cancel_creates_no_refund_and_deletes_no_data(self):
        attempts_before = PaymentAttempt.objects.filter(subscription=self.subscription).count()
        self.client_a.post("/api/v1/billing/subscription/cancel/", **self.with_env(self.env_a.id))
        self.assertEqual(
            PaymentAttempt.objects.filter(subscription=self.subscription).count(), attempts_before
        )
        self.assertTrue(Subscription.objects.filter(pk=self.subscription.pk).exists())

    def test_cross_tenant_cancel_is_denied(self):
        self.assert_cross_tenant_denied("post", "/api/v1/billing/subscription/cancel/")

    def test_a_non_owner_member_of_the_same_environment_is_refused(self):
        student = self.make_student_in(self.env_a, "201020000097")
        from rest_framework.test import APIClient

        client = APIClient()
        client.force_authenticate(user=student)
        r = client.post("/api/v1/billing/subscription/cancel/", **self.with_env(self.env_a.id))
        self.assertIn(r.status_code, (401, 403))
        self.subscription.refresh_from_db()
        self.assertFalse(self.subscription.cancel_at_period_end)

    def test_anonymous_is_refused(self):
        from rest_framework.test import APIClient

        r = APIClient().post("/api/v1/billing/subscription/cancel/")
        self.assertEqual(r.status_code, 401)


class PaymentHistoryEndpointTests(TenantTestCase):
    """AC-BILL-031-1, AC-BILL-031-2, AC-BILL-031-3."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.subscription = _make_subscription(self.env_a, plan=self.plan)
        self.period = None
        from .models import BillingPeriod

        start = timezone.now() - timezone.timedelta(days=30)
        self.period = BillingPeriod.objects.create(
            environment=self.env_a, subscription=self.subscription,
            period_start=start, period_end=start + timezone.timedelta(days=30),
        )
        self.attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=self.subscription, billing_period=self.period,
            status=PaymentAttempt.Status.SUCCEEDED, merchant_order_id="hist-order-1",
            amount_minor_units=self.plan.price_minor_units,
            provider_transaction_id="txn-should-not-leak", provider_order_id="order-should-not-leak",
        )

    def test_the_owner_sees_their_payment_history(self):
        r = self.client_a.get("/api/v1/billing/history/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        rows = body["results"] if "results" in body else body
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(rows[0]["period_start"][:10], self.period.period_start.date().isoformat())

    def test_cross_tenant_read_is_denied(self):
        self.assert_cross_tenant_denied("get", "/api/v1/billing/history/")

    def test_response_never_contains_provider_transaction_or_order_ids(self):
        r = self.client_a.get("/api/v1/billing/history/", **self.with_env(self.env_a.id))
        raw = r.content.decode()
        for leaked in ("txn-should-not-leak", "order-should-not-leak", "provider_transaction_id", "provider_order_id", "merchant_order_id"):
            self.assertNotIn(leaked, raw, f"leaked {leaked!r}")

    def test_history_is_paginated_with_standard_pagination(self):
        r = self.client_a.get("/api/v1/billing/history/", **self.with_env(self.env_a.id))
        body = r.json()
        self.assertIn("results", body)
        self.assertIn("count", body)
