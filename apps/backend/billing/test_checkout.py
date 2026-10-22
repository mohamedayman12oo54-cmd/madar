"""
BILL-WU-019 — checkout initiation, correlation, redirect-return tests.

Uses `TenantTestCase` (`environments/tenancy_testing.py`), except for
AC-BILL-019-7 which needs a real (non test-wrapped) transaction boundary —
see `CheckoutProviderCallOutsideTransactionTests` below.
"""
from unittest.mock import patch

from django.db import connection
from django.test import TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from environments.models import Environment, EnvironmentMembership
from environments.tenancy import ACTIVE_ENVIRONMENT_HEADER
from environments.tenancy_testing import TenantTestCase

from .models import PaymentAttempt, Plan, Subscription
from .providers import FakePaymentProvider

_HEADER_KWARG = "HTTP_" + ACTIVE_ENVIRONMENT_HEADER.upper().replace("-", "_")


class CheckoutInitiationTests(TenantTestCase):
    """AC-BILL-019-1."""

    def test_a_teacher_owner_can_start_checkout_for_each_plan(self):
        for key in (Plan.Key.PLAN_1, Plan.Key.PLAN_2, Plan.Key.PLAN_3):
            plan = Plan.objects.get(key=key)
            r = self.client_a.post(
                "/api/v1/billing/checkout/", {"plan_key": key}, format="json", **self.with_env(self.env_a.id)
            )
            self.assertEqual(r.status_code, 201, r.content)
            body = r.json()
            self.assertTrue(body["session_url"])
            attempt = PaymentAttempt.objects.get(pk=body["attempt_id"])
            self.assertEqual(attempt.amount_minor_units, plan.price_minor_units)
            self.assertEqual(attempt.currency, plan.currency)
            self.assertEqual(attempt.environment_id, self.env_a.id)
            self.assertEqual(attempt.status, PaymentAttempt.Status.INITIATED)
            # Force this attempt terminal so the next plan in this loop
            # exercises the "create a fresh attempt" path, not the
            # "non-terminal attempt already exists" one (that's AC-4).
            attempt.status = PaymentAttempt.Status.FAILED
            attempt.save(update_fields=["status"])


class CheckoutMassAssignmentTests(TenantTestCase):
    """AC-BILL-019-2."""

    def test_sending_server_controlled_fields_has_no_effect(self):
        r = self.client_a.post(
            "/api/v1/billing/checkout/",
            {
                "plan_key": Plan.Key.PLAN_1,
                "amount": 1, "amount_minor_units": 1, "currency": "USD", "status": "succeeded",
                "environment_id": self.env_b.id,
            },
            format="json", **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 201, r.content)
        attempt = PaymentAttempt.objects.get(pk=r.json()["attempt_id"])
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.assertEqual(attempt.amount_minor_units, plan.price_minor_units)
        self.assertEqual(attempt.currency, plan.currency)
        self.assertEqual(attempt.status, PaymentAttempt.Status.INITIATED)
        self.assertEqual(attempt.environment_id, self.env_a.id)


class CheckoutReturnEndpointTests(TenantTestCase):
    """AC-BILL-019-3."""

    def setUp(self):
        super().setUp()
        r = self.client_a.post(
            "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json", **self.with_env(self.env_a.id)
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.attempt_id = r.json()["attempt_id"]

    def test_return_endpoint_with_success_looking_params_does_not_change_state(self):
        r = self.client_a.get(
            f"/api/v1/billing/checkout/return/?attempt_id={self.attempt_id}&status=SUCCESS&paymentStatus=paid",
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], PaymentAttempt.Status.INITIATED)

        attempt = PaymentAttempt.objects.get(pk=self.attempt_id)
        self.assertEqual(attempt.status, PaymentAttempt.Status.INITIATED)
        subscription = Subscription.objects.get(environment=self.env_a)
        self.assertEqual(subscription.state, Subscription.State.TRIAL)
        self.assertIsNone(subscription.current_period_start)

    def test_return_endpoint_without_attempt_id_is_safe(self):
        r = self.client_a.get("/api/v1/billing/checkout/return/?status=SUCCESS", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["attempt_id"])

    def test_return_endpoint_cannot_be_used_to_read_another_tenants_attempt(self):
        r = self.client_b.get(
            f"/api/v1/billing/checkout/return/?attempt_id={self.attempt_id}", **self.with_env(self.env_b.id)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["attempt_id"])


class CheckoutIdempotencyTests(TenantTestCase):
    """AC-BILL-019-4."""

    def test_a_second_checkout_request_returns_the_same_attempt(self):
        r1 = self.client_a.post(
            "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json", **self.with_env(self.env_a.id)
        )
        r2 = self.client_a.post(
            "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json", **self.with_env(self.env_a.id)
        )
        self.assertEqual(r1.status_code, 201, r1.content)
        self.assertEqual(r2.status_code, 201, r2.content)
        self.assertEqual(r1.json()["attempt_id"], r2.json()["attempt_id"])
        self.assertEqual(PaymentAttempt.objects.filter(environment=self.env_a).count(), 1)

    def test_a_second_request_naming_a_different_plan_is_refused_not_silently_reused(self):
        """Re-using the live attempt would charge the OLD plan's amount for the plan the teacher
        just clicked; voiding it could orphan a payment in progress. So: 409, one attempt."""
        r1 = self.client_a.post(
            "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json", **self.with_env(self.env_a.id)
        )
        r2 = self.client_a.post(
            "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_2}, format="json", **self.with_env(self.env_a.id)
        )
        self.assertEqual(r1.status_code, 201)
        self.assertEqual((r2.status_code, r2.json()["code"]), (409, "checkout_in_progress"))
        self.assertEqual(PaymentAttempt.objects.filter(environment=self.env_a).count(), 1)
        self.assertEqual(PaymentAttempt.objects.get(environment=self.env_a).plan.key, Plan.Key.PLAN_1)


class CheckoutPermissionTests(TenantTestCase):
    """AC-BILL-019-5."""

    def test_cross_tenant_checkout_is_denied(self):
        self.assert_cross_tenant_denied(
            "post", "/api/v1/billing/checkout/", body={"plan_key": Plan.Key.PLAN_1}, expect_status=403
        )

    def test_a_non_owner_member_of_the_same_environment_is_refused(self):
        student = self.make_student_in(self.env_a, "201020000097")
        client = APIClient()
        client.force_authenticate(user=student)
        r = client.post(
            "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json", **self.with_env(self.env_a.id)
        )
        self.assertIn(r.status_code, (401, 403))

    def test_anonymous_is_refused(self):
        r = APIClient().post("/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json")
        self.assertEqual(r.status_code, 401)


class CheckoutExpiredTrialTests(TenantTestCase):
    """AC-BILL-019-6."""

    def test_checkout_is_permitted_for_an_environment_whose_trial_has_expired(self):
        long_ago = timezone.now() - timezone.timedelta(days=100)
        Subscription.objects.create(environment=self.env_a, trial_started_at=long_ago)
        r = self.client_a.post(
            "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json", **self.with_env(self.env_a.id)
        )
        self.assertEqual(r.status_code, 201, r.content)


class CheckoutPaidPeriodActiveTests(TenantTestCase):
    """Expected outcome: no plan change while a paid period is active
    (OUT OF SCOPE per this unit; BILL-WU-039)."""

    def test_checkout_is_refused_while_a_paid_period_is_active(self):
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        now = timezone.now()
        Subscription.objects.create(
            environment=self.env_a, plan=plan, state=Subscription.State.ACTIVE,
            current_period_start=now - timezone.timedelta(days=1),
            current_period_end=now + timezone.timedelta(days=29),
        )
        r = self.client_a.post(
            "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_2}, format="json", **self.with_env(self.env_a.id)
        )
        self.assertEqual(r.status_code, 409, r.content)
        self.assertEqual(r.json()["code"], "paid_period_active")
        self.assertEqual(PaymentAttempt.objects.filter(environment=self.env_a).count(), 0)


class CheckoutProviderCallOutsideTransactionTests(TransactionTestCase):
    """AC-BILL-019-7. `TenantTestCase`'s base (`django.test.TestCase`) wraps
    every test in one outer atomic block, which would make
    `connection.in_atomic_block` always True regardless of this view's own
    behaviour — so this one test uses a real `TransactionTestCase` with its
    own minimal fixture instead."""

    def setUp(self):
        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="t", email="t-checkout-txn@example.com", phone="201020000077",
            password="Str0ng!Pass", is_active=True,
        )
        self.env = Environment.objects.create(owner=self.teacher, name="env")
        EnvironmentMembership.objects.create(
            user=self.teacher, environment=self.env, role=EnvironmentMembership.Role.OWNER
        )
        self.client_a = APIClient()
        r = self.client_a.post(
            "/api/v1/auth/teacher/login/", {"identifier": "t-checkout-txn@example.com", "password": "Str0ng!Pass"}
        )
        assert r.status_code == 200, r.content
        self.client_a.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])

    def test_provider_call_happens_outside_any_transaction(self):
        captured = {}
        original = FakePaymentProvider.create_recurring_setup_session

        def spy(self, attempt, plan, return_url):
            captured["in_atomic_block"] = connection.in_atomic_block
            return original(self, attempt, plan, return_url)

        with patch.object(FakePaymentProvider, "create_recurring_setup_session", spy):
            r = self.client_a.post(
                "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json",
                **{_HEADER_KWARG: str(self.env.id)},
            )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIn("in_atomic_block", captured)
        self.assertFalse(captured["in_atomic_block"])


class PendingCheckoutSurfaceTests(TenantTestCase):
    """The status endpoint tells the UI about a live checkout so it can offer to resume it."""

    def test_status_reports_no_pending_checkout_then_the_live_one_without_provider_ids(self):
        url = "/api/v1/billing/subscription/"
        self.assertIsNone(self.client_a.get(url, **self.with_env(self.env_a.id)).json()["pending_checkout"])
        self.client_a.post("/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_2}, format="json",
                           **self.with_env(self.env_a.id))
        body = self.client_a.get(url, **self.with_env(self.env_a.id)).json()["pending_checkout"]
        self.assertEqual((body["plan_key"], body["status"]), (Plan.Key.PLAN_2, "initiated"))
        self.assertEqual(set(body), {"attempt_id", "status", "plan_key"})

    def test_another_teachers_pending_checkout_is_never_visible(self):
        self.client_a.post("/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_2}, format="json",
                           **self.with_env(self.env_a.id))
        body = self.client_b.get("/api/v1/billing/subscription/", **self.with_env(self.env_b.id)).json()
        self.assertIsNone(body["pending_checkout"])
