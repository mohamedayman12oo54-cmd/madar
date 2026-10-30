"""
BILL-WU-018 — the Kashier adapter, tested against the reference vectors
Kashier publishes in its own docs plus a fake transport (no network).
"""
import hashlib
import hmac
import json
import urllib.parse
from unittest import mock

from django.test import SimpleTestCase, override_settings

from environments.tenancy_testing import TenantTestCase

from . import events
from .kashier import (
    TransportTimeout,
    KashierPaymentProvider,
    _amount_to_minor,
    _money_str,
    signature_payload,
)
from .models import PaymentAttempt, Plan, ProviderEvent, Subscription
from .providers import InvalidSignature, ProviderError

KASHIER = dict(
    PAYMENT_PROVIDER="kashier", KASHIER_MODE="test", KASHIER_MERCHANT_ID="mid-0-1",
    KASHIER_PAYMENT_API_KEY_TEST="11111", KASHIER_SECRET_KEY_TEST="test-secret",
    KASHIER_PAYMENT_API_KEY_LIVE="live-api-key", KASHIER_SECRET_KEY_LIVE="live-secret",
    KASHIER_WEBHOOK_URL="https://madar.example/api/v1/billing/webhooks/kashier/",
    KASHIER_AGREEMENT_PAYMENT_FREQUENCY="MONTHLY", KASHIER_AGREEMENT_MIN_DAYS_BETWEEN_PAYMENTS=28,
)

# The `data` object from Kashier's own "How the signature is computed" example.
DOC_DATA = {
    "amount": 1, "channel": "online | e-commerce", "currency": "EGP",
    "kashierOrderId": "9ad06b17-755b-4e21-9774-aff3e2726ac9", "merchantOrderId": "1653481557813",
    "method": "card", "orderReference": "TEST-ORD-38855", "status": "SUCCESS",
    "transactionId": "TX-249893963", "transactionResponseCode": "00",
}
DOC_DATA["signatureKeys"] = sorted(k for k in DOC_DATA)
DOC_DIGEST = "9610477b2255b2a8ef84fd89adfaa5f1305ff9c20324205851890f1ea03109f4"


def _sign(data, key="11111"):
    return hmac.new(key.encode(), signature_payload(data).encode(), hashlib.sha256).hexdigest()


def _body(data, event="pay"):
    return json.dumps({"event": event, "data": data}).encode()


class _Transport:
    def __init__(self, *responses):
        self.responses = list(responses)
        self.calls = []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, headers, json.loads(body) if body else None, timeout))
        item = self.responses.pop(0)
        if isinstance(item, Exception):
            raise item
        status, payload = item
        return status, json.dumps(payload).encode()


class _Attempt:
    merchant_order_id = "chk-abc"
    subscription_id = 7
    amount_minor_units = 100000
    currency = "EGP"


class _Plan:
    key = "plan_1"


@override_settings(**KASHIER)
class DocumentedVectorTests(SimpleTestCase):
    def test_the_signature_payload_and_digest_match_kashiers_published_example(self):
        self.assertIn("channel=online%20%7C%20e-commerce", signature_payload(DOC_DATA))
        self.assertEqual(_sign(DOC_DATA), DOC_DIGEST)

    def test_the_order_hash_matches_kashiers_published_example(self):
        provider = KashierPaymentProvider(transport=_Transport())
        self.assertEqual(
            provider.order_hash("99", "20", "EGP"),
            "606a8a1307d64caf4e2e9bb724738f115a8972c27eccb2a8acd9194c357e4bec",
        )


@override_settings(**KASHIER)
class WebhookVerificationTests(SimpleTestCase):
    def setUp(self):
        self.provider = KashierPaymentProvider(transport=_Transport())

    def _verify(self, data, signature=None, headers=None):
        headers = headers if headers is not None else {"x-kashier-signature": signature or _sign(data)}
        return self.provider.verify_and_parse_webhook(_body(data), headers)

    def test_a_correctly_signed_event_is_accepted_and_normalised(self):
        event = self._verify(DOC_DATA)
        self.assertEqual(event.outcome_status, "SUCCESS")
        self.assertEqual(event.merchant_order_id, "1653481557813")
        self.assertEqual(event.amount_minor_units, 100)
        self.assertEqual(event.provider_transaction_id, "TX-249893963")
        self.assertEqual(event.mode, "test")
        self.assertEqual(event.raw["agreement_ref"], "")

    def test_an_uppercase_hex_signature_is_accepted(self):
        self.assertTrue(self._verify(DOC_DATA, signature=_sign(DOC_DATA).upper()))

    def test_every_tampered_field_is_rejected(self):
        signature = _sign(DOC_DATA)
        for key, bad in (("amount", 1000), ("status", "FAILURE"), ("merchantOrderId", "other"),
                         ("currency", "USD"), ("transactionId", "TX-1")):
            tampered = dict(DOC_DATA, **{key: bad})
            with self.assertRaises(InvalidSignature, msg=key):
                self._verify(tampered, signature=signature)

    def test_missing_or_garbage_signature_is_rejected(self):
        for headers in ({}, {"x-kashier-signature": ""}, {"x-kashier-signature": "0" * 64}):
            with self.assertRaises(InvalidSignature):
                self._verify(DOC_DATA, headers=headers)

    def test_a_signature_made_with_the_other_modes_key_is_rejected(self):
        with self.assertRaises(InvalidSignature):
            self._verify(DOC_DATA, signature=_sign(DOC_DATA, key="live-api-key"))

    def test_the_secret_key_cannot_sign_webhooks(self):
        with self.assertRaises(InvalidSignature):
            self._verify(DOC_DATA, signature=_sign(DOC_DATA, key="test-secret"))

    def test_fields_not_covered_by_the_signature_are_refused(self):
        partial = dict(DOC_DATA, signatureKeys=["amount", "channel", "currency", "method"])
        with self.assertRaises(InvalidSignature):
            self._verify(partial)

    def test_malformed_bodies_are_invalid_signature_not_crashes(self):
        for raw in (b"", b"not json", b"[]", b'{"data": 5}', b'{"event":"pay"}'):
            with self.assertRaises(InvalidSignature):
                self.provider.verify_and_parse_webhook(raw, {"x-kashier-signature": "a" * 64})

    def test_a_signed_key_that_is_absent_or_null_is_refused(self):
        for broken in (dict(DOC_DATA, signatureKeys=DOC_DATA["signatureKeys"] + ["ghost"]),
                       dict(DOC_DATA, orderReference=None)):
            with self.assertRaises(InvalidSignature):
                self._verify(broken)

    def test_an_idempotency_replay_shares_the_dedup_key_of_the_original(self):
        original = self.provider.verify_and_parse_webhook(_body(DOC_DATA, "pay"), {"x-kashier-signature": _sign(DOC_DATA)})
        replay = self.provider.verify_and_parse_webhook(_body(DOC_DATA, "idempotency"), {"x-kashier-signature": _sign(DOC_DATA)})
        self.assertEqual(original.dedup_key, replay.dedup_key)

    def test_card_data_and_merchant_details_never_reach_the_stored_payload(self):
        data = dict(DOC_DATA, card={"cardInfo": {"cardHolderName": "Jane", "maskedCard": "511111******1118"}},
                    merchantDetails={"businessEmail": "x@y.z"})
        data["signatureKeys"] = DOC_DATA["signatureKeys"]
        event = self._verify(data)
        dumped = json.dumps(event.raw)
        for leaked in ("Jane", "511111", "x@y.z", "cardInfo", "businessEmail"):
            self.assertNotIn(leaked, dumped)

    def test_amounts_convert_exactly_or_become_an_impossible_sentinel(self):
        self.assertEqual(_amount_to_minor(1000), 100000)
        self.assertEqual(_amount_to_minor("1000.50"), 100050)
        self.assertEqual(_amount_to_minor(10.005), -1)
        self.assertEqual(_amount_to_minor("abc"), -1)
        self.assertEqual(_amount_to_minor(-5), -1)
        self.assertEqual(_money_str(100000), "1000")
        self.assertEqual(_money_str(150050), "1500.5")


@override_settings(**KASHIER)
class SetupSessionTests(SimpleTestCase):
    def _ok(self, url="https://payments.kashier.io/session/abc?mode=test"):
        return (201, {"sessionUrl": url, "_id": "sess-1"})

    def test_session_request_follows_the_documented_shape(self):
        transport = _Transport(self._ok())
        session = KashierPaymentProvider(transport=transport).create_recurring_setup_session(
            _Attempt(), _Plan(), "https://app.example/billing/return")
        method, url, headers, body, timeout = transport.calls[0]
        self.assertEqual((method, url), ("POST", "https://test-api.kashier.io/v3/payment/sessions"))
        self.assertEqual(headers["Authorization"], "test-secret")
        self.assertEqual(headers["api-key"], "11111")
        self.assertEqual(body["amount"], "1000")
        self.assertEqual(body["merchantOrderId"], "chk-abc")
        self.assertEqual(body["saveCard"], "forced")
        self.assertEqual(body["interactionSource"], "RECURRING")
        self.assertEqual(body["customer"]["reference"], "madar-sub-7")
        self.assertEqual(body["agreement"]["paymentFrequency"], "MONTHLY")
        self.assertEqual(body["serverWebhook"], KASHIER["KASHIER_WEBHOOK_URL"])
        self.assertEqual(session.provider_session_ref, "sess-1")
        self.assertEqual(timeout, 15)

    def test_it_refuses_while_the_cadence_is_unconfigured(self):
        with override_settings(KASHIER_AGREEMENT_PAYMENT_FREQUENCY="", KASHIER_AGREEMENT_MIN_DAYS_BETWEEN_PAYMENTS=0):
            transport = _Transport()
            with self.assertRaises(ProviderError):
                KashierPaymentProvider(transport=transport).create_recurring_setup_session(_Attempt(), _Plan(), "https://x")
            self.assertEqual(transport.calls, [])

    def test_a_non_https_webhook_url_is_refused(self):
        with override_settings(KASHIER_WEBHOOK_URL="http://madar.example/hook"):
            with self.assertRaises(ProviderError):
                KashierPaymentProvider(transport=_Transport()).create_recurring_setup_session(_Attempt(), _Plan(), "https://x")

    def test_a_session_url_that_is_not_kashiers_is_never_handed_to_the_browser(self):
        for evil in ("https://evil.example/pay", "http://payments.kashier.io/x", "https://kashier.io.evil.example/x",
                     "javascript:alert(1)"):
            with self.assertRaises(ProviderError, msg=evil):
                KashierPaymentProvider(transport=_Transport(self._ok(evil))).create_recurring_setup_session(
                    _Attempt(), _Plan(), "https://x")

    def test_a_provider_rejection_is_a_provider_error_without_secrets(self):
        with self.assertRaises(ProviderError) as ctx:
            KashierPaymentProvider(transport=_Transport((403, {"message": "nope"}))).create_recurring_setup_session(
                _Attempt(), _Plan(), "https://x")
        self.assertNotIn("test-secret", str(ctx.exception))

    def test_unconfigured_keys_refuse_to_construct(self):
        with override_settings(KASHIER_SECRET_KEY_TEST=""):
            with self.assertRaises(ProviderError):
                KashierPaymentProvider(transport=_Transport())


@override_settings(**KASHIER)
class ChargeTests(SimpleTestCase):
    REF = "tok-123|agr-456"

    def _charge(self, *responses):
        transport = _Transport(*responses)
        result = KashierPaymentProvider(transport=transport).charge_saved_agreement(_Attempt(), self.REF)
        return result, transport

    def test_request_shape_and_hash(self):
        result, transport = self._charge((200, {"status": "SUCCESS", "transactionId": "TX-1", "orderId": "O-1"}))
        method, url, headers, body, _ = transport.calls[0]
        self.assertEqual((method, url), ("POST", "https://test-fep.kashier.io/v3/orders"))
        expected_hash = hmac.new(b"11111", b"/?payment=mid-0-1.chk-abc.1000.EGP.madar-sub-7", hashlib.sha256).hexdigest()
        self.assertEqual(headers["Kashier-Hash"], expected_hash)
        self.assertEqual(body["apiOperation"], "PAY")
        self.assertEqual(body["interactionSource"], "CONTAUTH")
        self.assertEqual(body["paymentMethod"]["card"]["cardToken"], "tok-123")
        self.assertEqual(body["paymentMethod"]["card"]["agreement"], {"id": "agr-456"})
        self.assertEqual(body["order"], {"reference": "chk-abc", "amount": 1000, "currency": "EGP"})
        self.assertEqual(result.outcome, "succeeded")
        self.assertEqual(result.provider_transaction_id, "TX-1")

    def test_outcome_mapping_is_conservative(self):
        cases = [
            ((200, {"status": "FAILURE", "transactionId": "T", "transactionResponseCode": "05"}), "failed"),
            ((200, {"status": "PENDING", "transactionId": "T"}), "pending"),
            ((200, {"status": "SUCCESS"}), "unknown"),            # success without a transaction id: not proof
            ((200, {"response": {"status": "SUCCESS", "transactionId": "T"}}), "succeeded"),
            ((403, {"code": "INVALID_HASH_CHECK"}), "unknown"),   # rejected before charging: not a payment failure
            ((502, {"message": "bad gateway"}), "unknown"),
            ((200, {"weird": True}), "unknown"),
        ]
        for response, expected in cases:
            result, _ = self._charge(response)
            self.assertEqual(result.outcome, expected, response)

    def test_a_transport_timeout_is_unknown_never_failed(self):
        result, _ = self._charge(TransportTimeout("slow"))
        self.assertEqual(result.outcome, "unknown")

    def test_an_incomplete_stored_agreement_is_refused_before_any_call(self):
        transport = _Transport()
        for ref in ("", "only-token", "|agr"):
            with self.assertRaises(ProviderError):
                KashierPaymentProvider(transport=transport).charge_saved_agreement(_Attempt(), ref)
        self.assertEqual(transport.calls, [])


@override_settings(**KASHIER)
class LookupAndAgreementTests(SimpleTestCase):
    def _order(self, **over):
        order = {"merchantOrderId": "chk-abc", "orderId": "O-9", "status": "CAPTURED",
                 "transactions": [{"operation": "3dsecure_verify", "status": "SUCCESS", "transactionId": "T0"},
                                  {"operation": "pay", "status": "SUCCESS", "transactionId": "T1",
                                   "transactionResponseCode": "00"}],
                 "sourceOfFunds": {"cardInfo": {"cardDataToken": "tok-9", "agreement": {"id": "agr-9"}}}}
        order.update(over)
        return order

    def _lookup(self, *responses):
        return KashierPaymentProvider(transport=_Transport(*responses)).lookup_order("chk-abc")

    def test_a_paid_order_is_succeeded(self):
        result = self._lookup((200, {"data": [self._order()]}))
        self.assertEqual((result.outcome, result.provider_transaction_id, result.provider_order_id),
                         ("succeeded", "T1", "O-9"))

    def test_only_an_exact_merchant_order_id_counts(self):
        # Kashier's `search` is a partial match: a neighbouring id must never be mistaken for ours.
        neighbour = self._order(merchantOrderId="chk-abc-2")
        self.assertEqual(self._lookup((200, {"data": [neighbour]})).outcome, "unknown")

    def test_failed_pending_and_missing_orders(self):
        failed = self._order(transactions=[{"operation": "pay", "status": "FAILURE", "transactionId": "T"}])
        pending = self._order(transactions=[{"operation": "pay", "status": "PENDING", "transactionId": "T"}])
        self.assertEqual(self._lookup((200, {"data": [failed]})).outcome, "failed")
        self.assertEqual(self._lookup((200, {"data": [pending]})).outcome, "pending")
        self.assertEqual(self._lookup((200, {"data": []})).outcome, "unknown")
        self.assertEqual(self._lookup((500, {})).outcome, "unknown")
        self.assertEqual(self._lookup(TransportTimeout("x")).outcome, "unknown")

    def test_the_agreement_is_read_from_the_paid_order(self):
        ref = KashierPaymentProvider(transport=_Transport((200, {"data": [self._order()]}))).fetch_agreement("chk-abc", "madar-sub-7")
        self.assertEqual((ref.card_token, ref.agreement_id), ("tok-9", "agr-9"))

    def test_the_token_list_is_the_fallback_and_matches_the_customer_reference(self):
        bare = self._order(sourceOfFunds={})
        tokens = {"data": [{"customerReference": "someone-else", "token": "no", "agreementId": "no"},
                           {"customerReference": "madar-sub-7", "token": "tok-L", "agreementId": "agr-L"}]}
        transport = _Transport((200, {"data": [bare]}), (200, tokens))
        ref = KashierPaymentProvider(transport=transport).fetch_agreement("chk-abc", "madar-sub-7")
        self.assertEqual((ref.card_token, ref.agreement_id), ("tok-L", "agr-L"))
        self.assertEqual(transport.calls[1][2]["Authorization"], "test-secret")

    def test_no_agreement_is_none_not_an_error(self):
        self.assertIsNone(KashierPaymentProvider(transport=_Transport((200, {"data": []}))).fetch_agreement("chk-abc"))
        self.assertIsNone(KashierPaymentProvider(transport=_Transport(TransportTimeout("x"))).fetch_agreement("chk-abc"))


@override_settings(**KASHIER)
class KashierEndToEndTests(TenantTestCase):
    """Real adapter, real webhook endpoint, real event application — only the
    network is replaced."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)
        self.sub = Subscription.objects.create(environment=self.env_a, plan=self.plan, state=Subscription.State.TRIAL)
        self.attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=self.sub, merchant_order_id="chk-e2e",
            amount_minor_units=self.plan.price_minor_units, currency=self.plan.currency,
            status=PaymentAttempt.Status.PENDING,
        )
        self.data = dict(DOC_DATA, merchantOrderId="chk-e2e", amount=1000, transactionId="TX-E2E")
        self.data["signatureKeys"] = sorted(k for k in self.data if k != "signatureKeys")

    def _post(self, data=None, signature=None):
        data = data or self.data
        return self.client.post(
            "/api/v1/billing/webhooks/kashier/", data=_body(data), content_type="application/json",
            HTTP_X_KASHIER_SIGNATURE=signature or _sign(data),
        )

    def test_a_signed_success_activates_the_subscription_with_the_real_token(self):
        paid_order = {"data": [{"merchantOrderId": "chk-e2e", "orderId": "O-1", "transactions": [],
                                "sourceOfFunds": {"cardInfo": {"cardDataToken": "tok-real", "agreement": {"id": "agr-real"}}}}]}
        self.assertEqual(self._post().status_code, 200)
        event = ProviderEvent.objects.get()
        self.assertNotIn("tok-real", json.dumps(event.redacted_payload))
        with mock.patch("billing.kashier.default_transport",
                        return_value=(200, json.dumps(paid_order).encode())):
            events.apply(event)
        self.attempt.refresh_from_db()
        self.sub.refresh_from_db()
        self.assertEqual(self.attempt.status, PaymentAttempt.Status.SUCCEEDED)
        self.assertEqual(self.sub.state, Subscription.State.ACTIVE)
        self.assertEqual(self.sub.active_agreement.charge_ref(), "tok-real|agr-real")
        self.assertNotIn("tok-real", json.dumps(ProviderEvent.objects.get().redacted_payload))

    def test_payment_is_honoured_even_if_the_token_cannot_be_fetched(self):
        self.assertEqual(self._post().status_code, 200)
        with mock.patch("billing.kashier.default_transport", side_effect=TransportTimeout("down")):
            events.apply(ProviderEvent.objects.get())
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.state, Subscription.State.ACTIVE)
        self.assertIsNone(self.sub.active_agreement)

    def test_the_same_delivery_twice_is_stored_once_and_acknowledged(self):
        self.assertEqual(self._post().status_code, 200)
        self.assertEqual(self._post().status_code, 409)
        self.assertEqual(ProviderEvent.objects.count(), 1)

    def test_forged_and_wrong_amount_events_change_nothing(self):
        self.assertEqual(self._post(signature="0" * 64).status_code, 400)
        self.assertEqual(ProviderEvent.objects.count(), 0)
        cheap = dict(self.data, amount=1)
        cheap["signatureKeys"] = self.data["signatureKeys"]
        self.assertEqual(self._post(cheap).status_code, 200)  # authentic, but for the wrong amount
        events.apply(ProviderEvent.objects.get())
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.state, Subscription.State.TRIAL)

    def test_a_test_mode_signature_is_refused_when_running_live(self):
        with override_settings(KASHIER_MODE="live"):
            self.assertEqual(self._post().status_code, 400)
        self.assertEqual(ProviderEvent.objects.count(), 0)
