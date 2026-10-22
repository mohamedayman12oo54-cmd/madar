"""Abuse limits on the money endpoints: each request to these costs a DB row and/or an outbound provider call."""
from unittest import mock

from rest_framework.throttling import SimpleRateThrottle

from environments.tenancy_testing import TenantTestCase

from .models import Plan

RATES = SimpleRateThrottle.THROTTLE_RATES
CHECKOUT, CANCEL, WEBHOOK = "/api/v1/billing/checkout/", "/api/v1/billing/subscription/cancel/", "/api/v1/billing/webhooks/kashier/"


class BillingThrottleTests(TenantTestCase):
    def test_checkout_is_limited_per_teacher_and_the_limit_does_not_leak_to_another_teacher(self):
        body = {"plan_key": Plan.Key.PLAN_1}
        with mock.patch.dict(RATES, {"billing-checkout": "3/hour"}):
            codes = [self.client_a.post(CHECKOUT, body, format="json", **self.with_env(self.env_a.id)).status_code
                     for _ in range(5)]
            other = self.client_b.post(CHECKOUT, body, format="json", **self.with_env(self.env_b.id)).status_code
        self.assertEqual(codes[:3], [201, 201, 201])
        self.assertEqual(codes[3:], [429, 429])
        self.assertEqual(other, 201, "teacher B must not be throttled by teacher A's requests")

    def test_cancel_is_limited(self):
        with mock.patch.dict(RATES, {"billing-cancel": "2/hour"}):
            codes = [self.client_a.post(CANCEL, {}, format="json", **self.with_env(self.env_a.id)).status_code
                     for _ in range(4)]
        self.assertEqual(codes[2:], [429, 429])

    def test_status_polling_is_limited_but_has_room_for_the_ui_poll(self):
        """The UI polls every 3 s for 3 minutes (60 calls): the real limit must allow that."""
        self.assertEqual(RATES["billing-status"], "120/min")
        with mock.patch.dict(RATES, {"billing-status": "3/min"}):
            codes = [self.client_a.get("/api/v1/billing/subscription/", **self.with_env(self.env_a.id)).status_code
                     for _ in range(5)]
        self.assertEqual(codes[3:], [429, 429])

    def test_the_unauthenticated_webhook_is_rate_limited_per_ip_before_any_signature_work(self):
        with mock.patch.dict(RATES, {"billing-webhook": "3/min"}):
            codes = [self.client.post(WEBHOOK, data=b"{}", content_type="application/json").status_code
                     for _ in range(6)]
        self.assertEqual(codes[:3], [400, 400, 400])       # rejected (unsigned), but not yet throttled
        self.assertEqual(codes[3:], [429, 429, 429])

    def test_production_rates_are_generous_enough_for_provider_retries(self):
        self.assertEqual(RATES["billing-webhook"], "600/min")
        self.assertEqual(RATES["billing-checkout"], "10/hour")
