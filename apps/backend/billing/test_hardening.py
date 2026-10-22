"""
Part 2 hardening — money/security gaps found in review of the existing billing code.
Each test fails against the pre-fix code.
"""
import io

from django.test import RequestFactory, TestCase
from django.utils import timezone

from environments.tenancy_testing import TenantTestCase

from . import events
from .models import PaymentAttempt, Plan, ProviderEvent, Subscription
from .providers import FakePaymentProvider
from .webhooks import KashierWebhookView


class _ExplodingStream(io.BytesIO):
    def read(self, *a, **k):
        raise AssertionError("body was read although Content-Length is over the cap")


class WebhookSizeCapChecksHeaderFirstTests(TestCase):
    def test_a_huge_declared_length_is_refused_without_reading_the_body(self):
        request = RequestFactory().post(
            "/api/v1/billing/webhooks/kashier/", data=b"{}", content_type="application/json",
        )
        request.META["CONTENT_LENGTH"] = str(50 * 1024 * 1024)
        request._stream = _ExplodingStream(b"{}")
        request.META["wsgi.input"] = request._stream
        response = KashierWebhookView.as_view()(request)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(ProviderEvent.objects.count(), 0)


class MissingAmountMustNotActivateTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.sub = Subscription.objects.create(environment=self.env_a, plan=self.plan, state=Subscription.State.TRIAL)
        self.attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=self.sub, merchant_order_id="chk-h1",
            amount_minor_units=self.plan.price_minor_units, currency=self.plan.currency,
            status=PaymentAttempt.Status.PENDING,
        )

    def _event(self, payload):
        return ProviderEvent.objects.create(
            dedup_key="dk-h-" + str(ProviderEvent.objects.count()), mode="test", event_type="charge",
            transaction_status="SUCCESS", provider_transaction_id="t", provider_order_id="o",
            signature_valid=True, redacted_payload=payload,
        )

    def test_a_success_event_without_amount_and_currency_is_rejected(self):
        events.apply(self._event({"merchant_order_id": "chk-h1"}))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.PENDING)
        self.sub.refresh_from_db()
        self.assertNotEqual(self.sub.state, Subscription.State.ACTIVE)

    def test_a_success_event_with_the_right_amount_still_activates(self):
        events.apply(self._event({
            "merchant_order_id": "chk-h1", "amount_minor_units": self.plan.price_minor_units,
            "currency": self.plan.currency,
        }))
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.SUCCEEDED)

    def test_resubscribing_after_a_cancellation_clears_the_cancel_flag(self):
        self.sub.cancel_at_period_end = True
        self.sub.save(update_fields=["cancel_at_period_end"])
        events.apply(self._event({
            "merchant_order_id": "chk-h1", "amount_minor_units": self.plan.price_minor_units,
            "currency": self.plan.currency,
        }))
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.state, Subscription.State.ACTIVE)
        self.assertFalse(self.sub.cancel_at_period_end)


class ReturnEndpointRobustnessTests(TenantTestCase):
    def test_a_non_numeric_attempt_id_is_not_a_server_error(self):
        for bad in ("abc", "1;DROP TABLE", "99999999999999999999999", "-1", " "):
            r = self.client_a.get(
                "/api/v1/billing/checkout/return/", {"attempt_id": bad}, **self.with_env(self.env_a.id)
            )
            self.assertEqual(r.status_code, 200, (bad, r.content))
            self.assertIsNone(r.json()["attempt_id"])


class CheckoutIsThrottledTests(TenantTestCase):
    def test_hammering_checkout_gets_429(self):
        from django.core.cache import cache
        cache.clear()
        codes = []
        for _ in range(40):
            r = self.client_a.post(
                "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json",
                **self.with_env(self.env_a.id),
            )
            codes.append(r.status_code)
        self.assertIn(429, codes)
        cache.clear()


class UnavailableProviderIsACleanFailureTests(TenantTestCase):
    def test_checkout_with_an_unconfigured_provider_is_a_503_not_a_500(self):
        from django.test import override_settings
        with override_settings(PAYMENT_PROVIDER="kashier"):
            r = self.client_a.post(
                "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json",
                **self.with_env(self.env_a.id),
            )
        # 503, not 400: nothing is wrong with the request, the payment service is temporarily unavailable
        # (CheckoutView maps `provider_unavailable` to 503 on purpose; the web app shows a retry message).
        self.assertEqual(r.status_code, 503, r.content)
        self.assertEqual(r.json()["code"], "provider_unavailable")
        self.assertNotIn("kashier", r.content.decode().lower().replace("provider_unavailable", ""))

    def test_webhook_with_an_unconfigured_provider_is_a_503_and_stores_nothing(self):
        from django.test import override_settings
        with override_settings(PAYMENT_PROVIDER="kashier"):
            r = self.client.post(
                "/api/v1/billing/webhooks/kashier/", data=b"{}", content_type="application/json"
            )
        self.assertEqual(r.status_code, 503)
        self.assertEqual(ProviderEvent.objects.count(), 0)


class ReturnUrlPointsAtTheWebAppTests(TenantTestCase):
    """The browser returns to a FRONTEND page (display only — a redirect is never proof of payment). The
    page reads `attempt_id` from the query string and asks the server what really happened."""

    def _checkout_and_capture_return_url(self):
        seen = {}
        original = FakePaymentProvider.create_recurring_setup_session

        def spy(provider, attempt, plan, return_url):
            seen["return_url"] = return_url
            seen["attempt_id"] = attempt.pk
            return original(provider, attempt, plan, return_url)

        from unittest import mock
        with mock.patch.object(FakePaymentProvider, "create_recurring_setup_session", spy):
            r = self.client_a.post(
                "/api/v1/billing/checkout/", {"plan_key": Plan.Key.PLAN_1}, format="json",
                **self.with_env(self.env_a.id),
            )
        self.assertEqual(r.status_code, 201, r.content)
        return seen["return_url"], seen["attempt_id"]

    def test_the_configured_web_app_page_is_used(self):
        from django.test import override_settings
        with override_settings(BILLING_CHECKOUT_RETURN_URL="https://app.madar.example/app/billing"):
            url, attempt_id = self._checkout_and_capture_return_url()
        self.assertEqual(url, f"https://app.madar.example/app/billing?attempt_id={attempt_id}")

    def test_an_existing_query_string_is_extended_not_replaced(self):
        from django.test import override_settings
        with override_settings(BILLING_CHECKOUT_RETURN_URL="https://app.madar.example/app/billing?src=kashier"):
            url, attempt_id = self._checkout_and_capture_return_url()
        self.assertEqual(url, f"https://app.madar.example/app/billing?src=kashier&attempt_id={attempt_id}")

    def test_without_configuration_it_falls_back_to_the_local_web_app(self):
        # Development only: production refuses to start without BILLING_CHECKOUT_RETURN_URL (config/settings.py).
        from django.test import override_settings
        with override_settings(BILLING_CHECKOUT_RETURN_URL=""):
            url, attempt_id = self._checkout_and_capture_return_url()
        self.assertEqual(url, f"http://localhost:5173/app/billing?attempt_id={attempt_id}")
