"""
BILL-WU-034 — billing adversarial/security test suite. Extends the
repo's adversarial testing practice (`config/test_security_audit.py`) to
the new billing attack surface, as a suite that is part of `manage.py test`.

The entitlement-bypass category (gated AI submission via an alternative
route) lives in `config.test_security_audit.EntitlementBypassTests`
instead of here: it necessarily references `ai.models.AIOperation`, which
the static check in `billing.test_webhooks.NoAIIdempotencyReuseTests`
(AC-BILL-020-5, ADR-017) forbids anywhere under this directory — the same
reasoning already applied to `billing/test_entitlement_enforcement.py`
(BILL-WU-011). Worker-side re-check parity for that same category is
covered by `ai.tests.WorkerEntitlementRecheckTests` (BILL-WU-011).
"""
import hashlib
import hmac
import json

from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.permissions import AllowAny
from rest_framework.test import APIClient

from academics.models import Grade
from accounts.testing import make_enrollment
from environments.tenancy_testing import PASSWORD, TenantTestCase

from .models import AmountOwed, BillingPeriod, PaymentAttempt, Plan, ProviderEvent, RecurringAgreement, Subscription
from .providers import FakePaymentProvider

WEBHOOK_URL = "/api/v1/billing/webhooks/kashier/"
CHECKOUT_URL = "/api/v1/billing/checkout/"
CHECKOUT_RETURN_URL = "/api/v1/billing/checkout/return/"
CANCEL_URL = "/api/v1/billing/subscription/cancel/"
SUBSCRIPTION_URL = "/api/v1/billing/subscription/"
HISTORY_URL = "/api/v1/billing/history/"
PLANS_URL = "/api/v1/billing/plans/"


def _post_raw(client, raw_body, headers):
    kwargs = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    return client.post(WEBHOOK_URL, data=raw_body, content_type="application/json", **kwargs)


def _payload(**overrides):
    base = {
        "kind": "charge", "outcome_status": "SUCCESS", "merchant_order_id": "chk_sec_abc123",
        "provider_transaction_id": "txn-sec-1", "provider_order_id": "ord-sec-1",
        "amount_minor_units": 100000, "currency": "EGP", "mode": "test",
    }
    base.update(overrides)
    return base


def grant_plan(environment, plan_key):
    plan = Plan.objects.get(key=plan_key)
    now = timezone.now()
    subscription = Subscription.objects.create(
        environment=environment, plan=plan, state=Subscription.State.ACTIVE,
        current_period_start=now - timezone.timedelta(days=1), current_period_end=now + timezone.timedelta(days=29),
    )
    period = BillingPeriod.objects.create(
        environment=environment, subscription=subscription,
        period_start=subscription.current_period_start, period_end=subscription.current_period_end,
    )
    AmountOwed.objects.create(
        environment=environment, billing_period=period, amount_minor_units=plan.price_minor_units,
        currency=plan.currency, status=AmountOwed.Status.SATISFIED,
    )
    PaymentAttempt.objects.create(
        environment=environment, subscription=subscription, billing_period=period,
        merchant_order_id=f"sec-{subscription.pk}", amount_minor_units=plan.price_minor_units,
        currency=plan.currency, status=PaymentAttempt.Status.SUCCEEDED,
    )
    return subscription


class _Fixture(TenantTestCase):
    """Teacher A has an active subscription, a checkout attempt, and a
    recurring agreement — the billing rows Teacher B will attack."""

    def setUp(self):
        super().setUp()
        self.subscription = grant_plan(self.env_a, Plan.Key.PLAN_1)
        self.agreement = RecurringAgreement.objects.create(
            environment=self.env_a, subscription=self.subscription, card_token="super-secret-opaque-token",
            kashier_agreement_id="agr_shouldnotleak", mode=RecurringAgreement.Mode.TEST,
        )
        self.subscription.active_agreement = self.agreement
        self.subscription.save(update_fields=["active_agreement"])
        self.checkout_attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=self.subscription, merchant_order_id="sec-checkout-1",
            amount_minor_units=100000, currency="EGP", status=PaymentAttempt.Status.INITIATED,
            provider_transaction_id="txn-shouldnotleak", provider_order_id="order-shouldnotleak",
        )


class HorizontalPrivilegeTests(_Fixture):
    """Teacher B reading, cancelling, or checking out on Teacher A's
    environment via the header; guessing attempt ids."""

    def test_pointing_the_env_header_at_another_teacher_is_refused(self):
        for method, url, body in [
            ("get", SUBSCRIPTION_URL, None),
            ("get", HISTORY_URL, None),
            ("post", CANCEL_URL, None),
            ("post", CHECKOUT_URL, {"plan_key": Plan.Key.PLAN_1}),
        ]:
            with self.subTest(url=url):
                self.assert_cross_tenant_denied(method, url, body=body)
        self.subscription.refresh_from_db()
        self.assertFalse(self.subscription.cancel_at_period_end)  # the cancel attempt never landed

    def test_guessing_another_tenants_attempt_id_on_the_return_endpoint_reveals_nothing(self):
        r = self.client_b.get(
            f"{CHECKOUT_RETURN_URL}?attempt_id={self.checkout_attempt.id}", **self.with_env(self.env_b.id)
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["attempt_id"])
        self.assertIsNone(r.json()["status"])

    def test_a_large_random_attempt_id_is_handled_like_any_missing_one(self):
        r = self.client_a.get(f"{CHECKOUT_RETURN_URL}?attempt_id=999999999", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNone(r.json()["attempt_id"])


class VerticalPrivilegeTests(_Fixture):
    """Students and parents reaching billing endpoints."""

    def setUp(self):
        super().setUp()
        grade = Grade.objects.create(environment=self.env_a, name="g")
        self.student = self.make_student_in(self.env_a, "201555911111", "طالب")
        self.student.set_password(PASSWORD)
        self.student.is_active = True
        self.student.is_verified = True
        self.student.save()
        make_enrollment(self.env_a, self.student, grade)  # student_can_access() requires one
        self.sc = APIClient()
        tok = self.sc.post(
            "/api/v1/auth/student/login/", {"phone": self.student.phone, "password": PASSWORD}
        ).data["access"]
        self.sc.credentials(HTTP_AUTHORIZATION="Bearer " + tok)

    def test_a_student_cannot_reach_any_billing_endpoint(self):
        for method, url, body in [
            ("get", PLANS_URL, None),
            ("get", SUBSCRIPTION_URL, None),
            ("get", HISTORY_URL, None),
            ("post", CANCEL_URL, None),
            ("post", CHECKOUT_URL, {"plan_key": Plan.Key.PLAN_1}),
        ]:
            with self.subTest(url=url):
                fn = getattr(self.sc, method)
                r = fn(url, body, format="json", **self.with_env(self.env_a.id)) if body \
                    else fn(url, **self.with_env(self.env_a.id))
                self.assertIn(r.status_code, (401, 403), f"{url} -> {r.status_code}")

    def test_an_anonymous_caller_cannot_reach_any_billing_endpoint_except_the_webhook(self):
        anon = APIClient()
        for url in (PLANS_URL, SUBSCRIPTION_URL, HISTORY_URL, CANCEL_URL, CHECKOUT_URL):
            self.assertEqual(anon.get(url).status_code, 401, url)


class WebhookForgeryTests(TestCase):
    """Unsigned, wrong-key, other-mode, tampered, oversized, replayed,
    uncorrelated `merchantOrderId`, and amount-mismatch forgeries."""

    def test_an_unsigned_request_is_rejected(self):
        raw_body = json.dumps(_payload()).encode("utf-8")
        r = self.client.post(WEBHOOK_URL, data=raw_body, content_type="application/json")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 0)

    def test_a_wrong_key_signature_is_rejected(self):
        raw_body = json.dumps(_payload()).encode("utf-8")
        bad_signature = hmac.new(b"not-the-real-key", raw_body, hashlib.sha256).hexdigest()
        r = _post_raw(self.client, raw_body, {"X-Fake-Signature": bad_signature})
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 0)

    def test_a_validly_signed_other_mode_payload_is_rejected(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload(mode="live"))  # settings default is "test"
        r = _post_raw(self.client, raw_body, headers)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 0)

    def test_a_tampered_body_after_signing_is_rejected(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload())
        tampered = raw_body.replace(b"100000", b"1")
        r = _post_raw(self.client, tampered, headers)
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 0)

    def test_an_oversized_body_is_rejected_before_verification(self):
        huge = json.dumps(_payload(extra="x" * 70_000)).encode("utf-8")
        r = self.client.post(WEBHOOK_URL, data=huge, content_type="application/json", HTTP_X_FAKE_SIGNATURE="whatever")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 0)

    def test_a_replayed_valid_event_is_deduped_not_double_applied(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload())
        r1 = _post_raw(self.client, raw_body, headers)
        r2 = _post_raw(self.client, raw_body, headers)
        self.assertEqual(r1.status_code, 200, r1.content)
        self.assertEqual(r2.status_code, 409, r2.content)
        self.assertEqual(ProviderEvent.objects.count(), 1)

    def test_an_uncorrelated_merchant_order_id_is_received_but_never_applied(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload(merchant_order_id="no-such-attempt-exists"))
        r = _post_raw(self.client, raw_body, headers)
        self.assertEqual(r.status_code, 200, r.content)

        call_command("process_billing_events")

        event = ProviderEvent.objects.get()
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY)

    def test_an_amount_mismatched_event_is_received_but_never_applied(self):
        teacher_env = _FakeTenant.make()
        subscription = grant_plan(teacher_env, Plan.Key.PLAN_1)
        attempt = PaymentAttempt.objects.create(
            environment=teacher_env, subscription=subscription, merchant_order_id="sec-amount-mismatch",
            amount_minor_units=100000, currency="EGP", status=PaymentAttempt.Status.INITIATED,
        )
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(
            _payload(merchant_order_id="sec-amount-mismatch", amount_minor_units=1)
        )
        r = _post_raw(self.client, raw_body, headers)
        self.assertEqual(r.status_code, 200, r.content)

        call_command("process_billing_events")

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.INITIATED)  # never advanced to SUCCEEDED


class _FakeTenant:
    """Minimal standalone Environment/teacher pair for `TestCase`-based
    tests that don't need the full two-teacher `TenantTestCase` fixture."""

    @staticmethod
    def make():
        from accounts.models import User
        from environments.models import Environment, EnvironmentMembership

        teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="t", email=f"t-sec-{timezone.now().timestamp()}@example.com",
            phone=f"20109{int(timezone.now().timestamp() * 1000) % 10**7:07d}", password="Str0ng!Pass", is_active=True,
        )
        env = Environment.objects.create(owner=teacher, name="env")
        EnvironmentMembership.objects.create(user=teacher, environment=env, role=EnvironmentMembership.Role.OWNER)
        return env


class RedirectSpoofingTests(_Fixture):
    """The return endpoint with "success"-looking parameters changes
    nothing — ADR-016: a redirect is never proof of payment."""

    def test_success_looking_query_params_never_change_attempt_state(self):
        r = self.client_a.get(
            f"{CHECKOUT_RETURN_URL}?attempt_id={self.checkout_attempt.id}"
            "&status=SUCCESS&paymentStatus=paid&transaction_status=SUCCESS",
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], PaymentAttempt.Status.INITIATED)
        self.checkout_attempt.refresh_from_db()
        self.assertEqual(self.checkout_attempt.status, PaymentAttempt.Status.INITIATED)


class MassAssignmentTests(_Fixture):
    """Price, amount, plan cap, status, and environment fields in checkout
    and cancel bodies."""

    def test_checkout_body_cannot_override_server_controlled_fields(self):
        # env_b (not env_a — this fixture already gave env_a an ACTIVE paid
        # period, which would correctly refuse ANY new checkout with 409
        # regardless of mass-assignment; env_b has no Subscription yet, so
        # this actually exercises what gets stored on a real new attempt.
        r = self.client_b.post(
            CHECKOUT_URL,
            {
                "plan_key": Plan.Key.PLAN_1, "amount_minor_units": 1, "currency": "USD", "status": "succeeded",
                "environment_id": self.env_a.id, "student_cap": 999999,
            },
            format="json", **self.with_env(self.env_b.id),
        )
        self.assertEqual(r.status_code, 201, r.content)
        attempt = PaymentAttempt.objects.get(pk=r.json()["attempt_id"])
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.assertEqual(attempt.amount_minor_units, plan.price_minor_units)
        self.assertEqual(attempt.currency, plan.currency)
        self.assertEqual(attempt.environment_id, self.env_b.id)

    def test_cancel_body_extra_fields_have_no_effect_beyond_the_flag(self):
        r = self.client_a.post(
            CANCEL_URL,
            {
                "cancel_at_period_end": False, "environment_id": self.env_b.id, "reason": "ignore me",
                "renewal_already_in_progress": True,
            },
            format="json", **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["cancel_at_period_end"])  # the body's False is ignored
        self.subscription.refresh_from_db()
        self.assertEqual(self.subscription.environment_id, self.env_a.id)


class LeakageTests(_Fixture):
    """Tokens, agreement ids, secrets and raw payloads never in responses
    or error bodies; 500s are generic."""

    def test_subscription_and_history_never_leak_tokens_or_provider_ids(self):
        for url in (SUBSCRIPTION_URL, HISTORY_URL):
            raw = self.client_a.get(url, **self.with_env(self.env_a.id)).content.decode()
            for leaked in (
                "super-secret-opaque-token", "agr_shouldnotleak", "card_token", "kashier_agreement_id",
                "txn-shouldnotleak", "order-shouldnotleak", "provider_transaction_id", "provider_order_id",
                "merchant_order_id",
            ):
                self.assertNotIn(leaked, raw, f"{url} leaked {leaked!r}")

    def test_cancel_and_checkout_error_bodies_never_leak_internals(self):
        with override_settings(DEBUG=False):
            r = self.client_a.get(f"{HISTORY_URL}?page=not-a-number", **self.with_env(self.env_a.id))
            body = r.content.decode()
            for leaked in ("Traceback", "/home/", "site-packages", "SELECT ", "django.db"):
                self.assertNotIn(leaked, body)

    def test_webhook_errors_never_echo_the_rejected_payload(self):
        raw_body = json.dumps(_payload(merchant_order_id="should-not-echo-back")).encode("utf-8")
        r = self.client.post(WEBHOOK_URL, data=raw_body, content_type="application/json")
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("should-not-echo-back", r.content.decode())


class InboundSurfaceGuardTests(SimpleTestCase):
    """AC-BILL-034's own required check, scoped to `billing`: exactly one
    `AllowAny` route exists under `billing.urls` — the Kashier webhook.
    The project-WIDE enumeration (every app) already exists and is kept
    in sync separately: `billing.test_webhooks.AllowAnyRouteEnumerationTests`
    (BILL-WU-020) — not duplicated here to avoid two copies of the same
    expected set drifting apart."""

    def test_exactly_one_allow_any_view_exists_under_billing_urls(self):
        from billing import urls as billing_urls

        found = set()
        for pattern in billing_urls.urlpatterns:
            view_class = getattr(pattern.callback, "view_class", None)
            if view_class is not None and AllowAny in getattr(view_class, "permission_classes", ()):
                found.add(f"{view_class.__module__}.{view_class.__qualname__}")
        self.assertEqual(found, {"billing.webhooks.KashierWebhookView"})
