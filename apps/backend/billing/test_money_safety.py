"""
Money-state safety regressions found while auditing the payment path, plus an end-to-end run of the
REAL Kashier adapter through the webhook view. Each test names the failure it prevents.
"""
import json
from datetime import timedelta

from django.db import IntegrityError, transaction
from django.test import override_settings
from django.utils import timezone

from environments.tenancy_testing import TenantTestCase

from . import entitlements
from .models import PaymentAttempt, Plan, ProviderEvent, RecurringAgreement, Subscription, BillingPeriod
from billing.providers.kashier import webhook_signature
from billing.test_support import CONFIG, DOC_KEY

CHECKOUT = "/api/v1/billing/checkout/"
WEBHOOK = "/api/v1/billing/webhooks/kashier/"


def past_due_on_plan_1(environment):
    """A teacher whose last paid period ended and whose renewal FAILED (access still granted, with
    Plan 1's capabilities, until BILL-DEC-05 defines grace)."""
    plan = Plan.objects.get(key=Plan.Key.PLAN_1)
    now = timezone.now()
    sub = Subscription.objects.create(
        environment=environment, plan=plan, state=Subscription.State.PAST_DUE,
        current_period_start=now - timedelta(days=40), current_period_end=now - timedelta(days=10),
    )
    period = BillingPeriod.objects.create(
        environment=environment, subscription=sub, period_start=sub.current_period_start, period_end=sub.current_period_end,
    )
    PaymentAttempt.objects.create(
        environment=environment, subscription=sub, billing_period=period, merchant_order_id="renew_failed",
        amount_minor_units=plan.price_minor_units, currency="EGP", status=PaymentAttempt.Status.FAILED, plan=plan,
    )
    return sub


class StartingCheckoutNeverGrantsAPlanTests(TenantTestCase):
    def test_starting_a_plan_3_checkout_during_grace_does_not_upgrade_capabilities_or_cap(self):
        """BUG (fixed): start_checkout used to write Subscription.plan BEFORE payment, and decide()
        derives capabilities/cap from that field — so a past-due Plan 1 teacher got Plan 3 features and
        unlimited students just by pressing the button."""
        sub = past_due_on_plan_1(self.env_a)
        before = entitlements.decide(self.env_a)
        self.assertEqual(before.student_cap, 400)

        r = self.client_a.post(CHECKOUT, {"plan_key": Plan.Key.PLAN_3}, format="json", **self.with_env(self.env_a.id))

        self.assertEqual(r.status_code, 201, r.content)
        sub.refresh_from_db()
        self.assertEqual(sub.plan.key, Plan.Key.PLAN_1)
        after = entitlements.decide(self.env_a)
        self.assertEqual((after.capabilities, after.student_cap), (before.capabilities, 400))
        self.assertNotIn("ai.performance_analysis", after.capabilities)

    def test_the_attempt_remembers_the_plan_it_buys(self):
        r = self.client_a.post(CHECKOUT, {"plan_key": Plan.Key.PLAN_2}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(PaymentAttempt.objects.get(environment=self.env_a).plan.key, Plan.Key.PLAN_2)

    def test_resuming_the_same_plan_returns_the_same_attempt(self):
        a = self.client_a.post(CHECKOUT, {"plan_key": Plan.Key.PLAN_2}, format="json", **self.with_env(self.env_a.id))
        b = self.client_a.post(CHECKOUT, {"plan_key": Plan.Key.PLAN_2}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(a.json()["attempt_id"], b.json()["attempt_id"])

    def test_two_live_checkouts_for_one_subscription_are_structurally_impossible(self):
        sub = Subscription.objects.create(environment=self.env_a)
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        make = lambda oid: PaymentAttempt.objects.create(
            environment=self.env_a, subscription=sub, merchant_order_id=oid, amount_minor_units=1, plan=plan)
        make("chk_1")
        with self.assertRaises(IntegrityError), transaction.atomic():
            make("chk_2")

    def test_a_finished_checkout_does_not_block_a_new_one(self):
        sub = Subscription.objects.create(environment=self.env_a)
        plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        PaymentAttempt.objects.create(environment=self.env_a, subscription=sub, merchant_order_id="chk_old",
                                      amount_minor_units=1, plan=plan, status=PaymentAttempt.Status.FAILED)
        PaymentAttempt.objects.create(environment=self.env_a, subscription=sub, merchant_order_id="chk_new",
                                      amount_minor_units=1, plan=plan)


def kashier_event(attempt, *, amount_minor=None, status="SUCCESS", currency="EGP", txn="TX-100",
                  token="tok-REAL-1234567890", agreement="agr-REAL-0987654321", drop=()):
    amount_minor = attempt.amount_minor_units if amount_minor is None else amount_minor
    data = {"amount": amount_minor / 100, "currency": currency, "merchantOrderId": attempt.merchant_order_id,
            "status": status, "transactionId": txn, "kashierOrderId": "KO-1", "cardDataToken": token,
            "agreementId": agreement, "method": "card", "transactionResponseCode": "00"}
    keys = ["amount", "currency", "kashierOrderId", "merchantOrderId", "method", "status", "transactionId",
            "transactionResponseCode"]
    data["signatureKeys"] = [k for k in keys if k not in drop]
    body = json.dumps({"event": "pay", "data": data}).encode()
    return body, webhook_signature({**data, "signatureKeys": data["signatureKeys"]}, DOC_KEY)


@override_settings(**CONFIG)
class EndToEndThroughTheRealAdapterTests(TenantTestCase):
    def start(self, plan_key=Plan.Key.PLAN_2):
        # Session creation uses the fake (no network); only WEBHOOK verification uses the real adapter.
        with self.settings(PAYMENT_PROVIDER="fake"):
            self.client_a.post(CHECKOUT, {"plan_key": plan_key}, format="json", **self.with_env(self.env_a.id))
        return PaymentAttempt.objects.get(environment=self.env_a)

    def post(self, body, sig):
        return self.client.post(WEBHOOK, data=body, content_type="application/json", HTTP_X_KASHIER_SIGNATURE=sig)

    def test_a_signed_success_activates_the_purchased_plan_and_stores_the_real_token(self):
        """BUG (fixed): the stored payload is redacted, so the agreement reference used for renewals
        was a MASKED string (`*****7890`). The real references now travel in dedicated fields."""
        attempt = self.start(Plan.Key.PLAN_2)
        body, sig = kashier_event(attempt)

        r = self.post(body, sig)

        self.assertEqual(r.status_code, 200)
        attempt.refresh_from_db()
        sub = Subscription.objects.get(environment=self.env_a)
        self.assertEqual(attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual((sub.state, sub.plan.key), (Subscription.State.ACTIVE, Plan.Key.PLAN_2))
        self.assertEqual(sub.current_period_end - sub.current_period_start, timedelta(days=30))
        agreement = RecurringAgreement.objects.get(subscription=sub)
        self.assertEqual((agreement.card_token, agreement.kashier_agreement_id),
                         ("tok-REAL-1234567890", "agr-REAL-0987654321"))
        self.assertEqual(entitlements.decide(self.env_a).student_cap, 800)

    def test_the_stored_event_never_keeps_the_token_and_is_scrubbed_after_applying(self):
        attempt = self.start()
        body, sig = kashier_event(attempt)
        self.post(body, sig)
        event = ProviderEvent.objects.get()
        self.assertEqual((event.agreement_token, event.agreement_id), ("", ""))
        self.assertNotIn("tok-REAL", json.dumps(event.redacted_payload))
        self.assertNotIn("agr-REAL-0987654321", json.dumps(event.redacted_payload))

    def test_replaying_the_same_signed_event_never_double_applies(self):
        attempt = self.start()
        body, sig = kashier_event(attempt)
        first, second = self.post(body, sig), self.post(body, sig)
        self.assertEqual((first.status_code, second.status_code), (200, 409))
        self.assertEqual(RecurringAgreement.objects.count(), 1)
        self.assertEqual(BillingPeriod.objects.count(), 1)

    def test_a_forged_or_tampered_event_changes_nothing(self):
        attempt = self.start()
        body, sig = kashier_event(attempt)
        tampered = json.loads(body)
        tampered["data"]["amount"] = 0.01
        r = self.post(json.dumps(tampered).encode(), sig)
        self.assertEqual(r.status_code, 400)
        r = self.post(body, "0" * 64)
        self.assertEqual(r.status_code, 400)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.INITIATED)
        self.assertEqual((ProviderEvent.objects.count(), BillingPeriod.objects.count()), (0, 0))

    def test_a_signed_event_that_does_not_cover_the_amount_is_rejected(self):
        attempt = self.start()
        body, sig = kashier_event(attempt, drop=("amount",))
        self.assertEqual(self.post(body, sig).status_code, 400)
        self.assertEqual(ProviderEvent.objects.count(), 0)

    def test_underpaying_is_never_credited(self):
        """Signed but for the wrong amount (e.g. a cheaper plan's session paid against a dearer
        attempt): stored, flagged for a human, and NO access is granted."""
        attempt = self.start(Plan.Key.PLAN_3)
        body, sig = kashier_event(attempt, amount_minor=attempt.amount_minor_units - 100000)
        self.assertEqual(self.post(body, sig).status_code, 200)
        attempt.refresh_from_db()
        event = ProviderEvent.objects.get()
        self.assertEqual(attempt.status, PaymentAttempt.Status.INITIATED)
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY)
        self.assertIn("mismatch", event.last_error)
        self.assertFalse(entitlements.decide(self.env_a).access_granted and
                         entitlements.decide(self.env_a).basis == entitlements.Basis.PAID_ACTIVE)

    def test_wrong_currency_is_never_credited(self):
        attempt = self.start()
        body, sig = kashier_event(attempt, currency="USD")
        self.post(body, sig)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.INITIATED)

    def test_a_signed_failure_marks_the_attempt_failed_and_activates_nothing(self):
        attempt = self.start()
        body, sig = kashier_event(attempt, status="FAILURE")
        self.post(body, sig)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)
        self.assertEqual(RecurringAgreement.objects.count(), 0)
        sub = Subscription.objects.get(environment=self.env_a)
        self.assertNotEqual(sub.state, Subscription.State.ACTIVE)

    def test_an_event_for_an_unknown_order_is_stored_but_changes_no_state(self):
        attempt = self.start()
        attempt.merchant_order_id = "chk_not_ours"
        body, sig = kashier_event(attempt)
        self.assertEqual(self.post(body, sig).status_code, 200)
        self.assertEqual(ProviderEvent.objects.get().processing_status, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY)
        self.assertEqual(RecurringAgreement.objects.count(), 0)

    def test_a_success_arriving_after_a_terminal_failure_is_not_applied(self):
        attempt = self.start()
        self.post(*kashier_event(attempt, status="FAILURE", txn="TX-1"))
        self.post(*kashier_event(attempt, status="SUCCESS", txn="TX-2"))
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, PaymentAttempt.Status.FAILED)
        self.assertEqual(RecurringAgreement.objects.count(), 0)

    @override_settings(KASHIER_MODE="live")
    def test_a_test_mode_event_is_rejected_by_a_live_deployment(self):
        attempt = self.start()
        data = json.loads(kashier_event(attempt)[0])["data"]
        data["mode"] = "test"
        body = json.dumps({"event": "pay", "data": data}).encode()
        sig = webhook_signature(data, "live-payment-key")
        self.assertEqual(self.post(body, sig).status_code, 400)
        self.assertEqual(ProviderEvent.objects.count(), 0)
