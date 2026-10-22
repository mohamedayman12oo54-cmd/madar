"""
BILL-WU-018 — Kashier adapter tests (synthetic fixtures; no network, no real keys).

The two known-good vectors below are published in Kashier's own docs
(developers.kashier.io: "Request hashing" and "Webhooks", reviewed 2026-10-20) using the
illustrative key ``11111``; they pin our signing code to Kashier's, not just to itself.
"""
import hashlib
import hmac
import json
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, override_settings

from billing.providers import InvalidSignature, ProviderError, get_payment_provider
from billing.providers import kashier as k
from billing.providers.kashier import KashierProvider

from billing.test_support import CONFIG, DOC_KEY  # noqa: E402

DOC_DATA = {
    "amount": 1, "channel": "online | e-commerce", "currency": "EGP",
    "kashierOrderId": "9ad06b17-755b-4e21-9774-aff3e2726ac9", "merchantOrderId": "1653481557813",
    "method": "card", "orderReference": "TEST-ORD-38855", "status": "SUCCESS",
    "transactionId": "TX-249893963", "transactionResponseCode": "00",
    "signatureKeys": ["amount", "channel", "currency", "kashierOrderId", "merchantOrderId", "method",
                      "orderReference", "status", "transactionId", "transactionResponseCode"],
}


def sign(data, key=DOC_KEY):
    return k.webhook_signature(data, key)


def webhook(data, event="pay", key=DOC_KEY):
    body = json.dumps({"event": event, "data": data}).encode()
    return body, {"x-kashier-signature": sign(data, key)}


class OfficialVectorTests(SimpleTestCase):
    def test_webhook_signature_matches_kashiers_published_digest(self):
        self.assertEqual(sign(DOC_DATA), "9610477b2255b2a8ef84fd89adfaa5f1305ff9c20324205851890f1ea03109f4")

    def test_order_hash_matches_kashiers_published_digest(self):
        self.assertEqual(
            k.order_hash("mid-0-1", "99", "20", "EGP", "", DOC_KEY),
            "606a8a1307d64caf4e2e9bb724738f115a8972c27eccb2a8acd9194c357e4bec",
        )

    def test_customer_reference_is_appended_when_present(self):
        with_ref = k.order_hash("m", "o", "1", "EGP", "cust", DOC_KEY)
        expected = hmac.new(DOC_KEY.encode(), b"/?payment=m.o.1.EGP.cust", hashlib.sha256).hexdigest()
        self.assertEqual(with_ref, expected)

    def test_amount_formatting(self):
        self.assertEqual(k.amount_text(2000), "20")
        self.assertEqual(k.amount_text(150050), "1500.5")
        self.assertEqual(k.minor_units_from(1500), 150000)
        self.assertEqual(k.minor_units_from("20.50"), 2050)
        with self.assertRaises(ValueError):
            k.minor_units_from("10.005")       # never round money silently
        with self.assertRaises(ValueError):
            k.minor_units_from(-1)


@override_settings(**CONFIG)
class WebhookVerificationTests(SimpleTestCase):
    def setUp(self):
        self.p = KashierProvider()

    def test_a_correctly_signed_event_is_parsed_into_the_neutral_shape(self):
        data = {**DOC_DATA, "amount": 1000, "cardDataToken": "tok-1", "agreementId": "agr-1"}
        body, headers = webhook(data)
        event = self.p.verify_and_parse_webhook(body, headers)
        self.assertEqual(
            (event.outcome_status, event.kind, event.amount_minor_units, event.currency, event.mode),
            ("SUCCESS", "pay", 100000, "EGP", "test"),
        )
        self.assertEqual((event.merchant_order_id, event.provider_transaction_id), ("1653481557813", "TX-249893963"))
        self.assertEqual((event.card_token, event.agreement_ref), ("tok-1", "agr-1"))

    def test_the_token_is_found_in_a_nested_container_too(self):
        data = {**DOC_DATA, "card": {"cardToken": "nested-tok"}, "agreement": {"agreementId": "nested-agr"}}
        body, headers = webhook(data)
        event = self.p.verify_and_parse_webhook(body, headers)
        self.assertEqual((event.card_token, event.agreement_ref), ("nested-tok", "nested-agr"))

    def test_uppercase_hex_signature_is_accepted(self):
        body, headers = webhook(DOC_DATA)
        headers["x-kashier-signature"] = headers["x-kashier-signature"].upper()
        self.assertEqual(self.p.verify_and_parse_webhook(body, headers).outcome_status, "SUCCESS")

    def test_every_tamper_is_rejected(self):
        for field, value in (("amount", 1), ("amount", 99999), ("status", "FAILURE"), ("currency", "USD"),
                             ("merchantOrderId", "someone-else"), ("transactionId", "TX-1")):
            data = {**DOC_DATA, "amount": 1000}
            body, headers = webhook(data)
            tampered = json.loads(body)
            tampered["data"][field] = value if tampered["data"][field] != value else "x"
            with self.assertRaises(InvalidSignature, msg=field):
                self.p.verify_and_parse_webhook(json.dumps(tampered).encode(), headers)

    def test_wrong_missing_and_garbage_signatures_are_rejected(self):
        body, _ = webhook(DOC_DATA)
        for headers in ({}, {"x-kashier-signature": ""}, {"x-kashier-signature": "0" * 64},
                        {"x-kashier-signature": "not-hex"}):
            with self.assertRaises(InvalidSignature):
                self.p.verify_and_parse_webhook(body, headers)

    def test_a_signature_made_with_the_other_modes_key_is_rejected(self):
        body, headers = webhook(DOC_DATA, key="live-payment-key")
        with self.assertRaises(InvalidSignature):
            self.p.verify_and_parse_webhook(body, headers)

    @override_settings(KASHIER_MODE="live")
    def test_in_live_mode_only_the_live_key_validates(self):
        body, headers = webhook(DOC_DATA, key="live-payment-key")
        self.assertEqual(self.p.verify_and_parse_webhook(body, headers).mode, "live")
        body, headers = webhook(DOC_DATA, key=DOC_KEY)            # the TEST key must not work live
        with self.assertRaises(InvalidSignature):
            self.p.verify_and_parse_webhook(body, headers)

    def test_an_event_that_does_not_sign_the_fields_we_act_on_is_rejected(self):
        """A validly signed message that omits e.g. `status` from signatureKeys would let an attacker
        replaying it edit the unsigned field. We refuse such events outright."""
        for dropped in ("status", "amount", "merchantOrderId", "currency", "transactionId"):
            data = {**DOC_DATA, "signatureKeys": [x for x in DOC_DATA["signatureKeys"] if x != dropped]}
            body, headers = webhook(data)
            with self.assertRaises(InvalidSignature, msg=dropped):
                self.p.verify_and_parse_webhook(body, headers)

    def test_signature_keys_naming_an_absent_field_are_rejected(self):
        data = {**DOC_DATA, "signatureKeys": DOC_DATA["signatureKeys"] + ["ghost"]}
        body = json.dumps({"event": "pay", "data": data}).encode()
        with self.assertRaises(InvalidSignature):
            self.p.verify_and_parse_webhook(body, {"x-kashier-signature": "a" * 64})

    def test_malformed_bodies_are_rejected_not_crashing(self):
        for body in (b"", b"not json", b"[]", b"{}", b'{"data": 1}', b'{"data": {"signatureKeys": "x"}}',
                     b'{"data": {"signatureKeys": []}}'):
            with self.assertRaises(InvalidSignature):
                self.p.verify_and_parse_webhook(body, {"x-kashier-signature": "a" * 64})

    def test_a_non_exact_amount_is_rejected_even_when_signed(self):
        body, headers = webhook({**DOC_DATA, "amount": "10.005"})
        with self.assertRaises(InvalidSignature):
            self.p.verify_and_parse_webhook(body, headers)

    def test_values_needing_url_encoding_are_signed_like_kashier_does(self):
        data = {**DOC_DATA, "channel": "a b|c&d=e"}
        body, headers = webhook(data)
        self.assertEqual(self.p.verify_and_parse_webhook(body, headers).outcome_status, "SUCCESS")

    def test_an_event_claiming_the_other_mode_is_surfaced_so_the_view_can_reject_it(self):
        body, headers = webhook({**DOC_DATA, "mode": "live"})
        self.assertEqual(self.p.verify_and_parse_webhook(body, headers).mode, "live")


def attempt_stub(order_id="chk_abc", minor=100000):
    agreement = SimpleNamespace(kashier_agreement_id="agr-9")
    return SimpleNamespace(
        merchant_order_id=order_id, amount_minor_units=minor, currency="EGP", subscription_id=7,
        subscription=SimpleNamespace(active_agreement=agreement),
    )


class Recorder:
    def __init__(self, status=200, payload=None, raises=None):
        self.status, self.payload, self.raises, self.calls = status, payload or {}, raises, []

    def __call__(self, method, url, headers, body, timeout):
        self.calls.append((method, url, dict(headers), json.loads(body) if body else None, timeout))
        if self.raises:
            raise self.raises
        return self.status, json.dumps(self.payload).encode()


NOT_IN_TXN = mock.patch("billing.providers.kashier.connection", mock.Mock(in_atomic_block=False))


@override_settings(**CONFIG)
class OutboundCallTests(SimpleTestCase):
    def setUp(self):
        NOT_IN_TXN.start()
        self.addCleanup(NOT_IN_TXN.stop)
        self.plan = SimpleNamespace(name="الباقة الأولى")

    def provider(self, **kw):
        rec = Recorder(**kw)
        return KashierProvider(transport=rec), rec

    # ---- checkout session
    def test_session_request_carries_server_side_values_and_configured_agreement(self):
        p, rec = self.provider(payload={"sessionUrl": "https://payments.kashier.io/session/abc?mode=test", "_id": "sess1"})
        session = p.create_recurring_setup_session(attempt_stub(), self.plan, "https://app.example.com/app/billing?attempt_id=5")
        method, url, headers, body, timeout = rec.calls[0]
        self.assertEqual((method, url), ("POST", "https://test-api.kashier.io/v3/payment/sessions"))
        self.assertEqual((headers["Authorization"], headers["api-key"]), ("test-secret", DOC_KEY))
        self.assertEqual(body["amount"], "1000")
        self.assertEqual(body["merchantOrderId"], "chk_abc")
        self.assertEqual(body["serverWebhook"], CONFIG["KASHIER_WEBHOOK_URL"])
        self.assertEqual(body["merchantRedirect"], "https://app.example.com/app/billing?attempt_id=5")
        self.assertEqual(body["saveCard"], "forced")
        self.assertEqual(body["agreement"]["paymentFrequency"], "MONTHLY")
        self.assertEqual(body["agreement"]["minimumDaysBetweenPayments"], 25)
        self.assertEqual(timeout, k.HTTP_TIMEOUT_SECONDS)
        self.assertEqual((session.session_url, session.provider_session_ref),
                         ("https://payments.kashier.io/session/abc?mode=test", "sess1"))

    def test_a_checkout_url_on_an_untrusted_host_is_refused(self):
        for bad in ("https://evil.example.com/pay", "http://payments.kashier.io/x", "https://kashier.io.evil.com/x",
                    "javascript:alert(1)"):
            p, _ = self.provider(payload={"sessionUrl": bad, "_id": "s"})
            with self.assertRaises(ProviderError, msg=bad):
                p.create_recurring_setup_session(attempt_stub(), self.plan, "https://x/")

    def test_missing_agreement_parameters_refuse_session_creation(self):
        """BILL-EXT-01: nothing is defaulted — an unset cadence must stop checkout, never guess."""
        for name in ("KASHIER_AGREEMENT_PAYMENT_FREQUENCY", "KASHIER_AGREEMENT_MIN_DAYS_BETWEEN",
                     "KASHIER_AGREEMENT_TYPE", "KASHIER_AGREEMENT_EXPIRY_DATE", "KASHIER_AGREEMENT_NUMBER_OF_PAYMENTS"):
            with override_settings(**{name: ""}):
                p, rec = self.provider(payload={"sessionUrl": "https://payments.kashier.io/s", "_id": "s"})
                with self.assertRaises(ProviderError, msg=name):
                    p.create_recurring_setup_session(attempt_stub(), self.plan, "https://x/")
                self.assertEqual(rec.calls, [], "nothing may be sent with an incomplete agreement")

    @override_settings(KASHIER_MODE="live")
    def test_live_session_creation_is_refused_while_cadence_is_unset(self):
        with override_settings(KASHIER_AGREEMENT_PAYMENT_FREQUENCY=""):
            p, rec = self.provider()
            with self.assertRaises(ProviderError):
                p.create_recurring_setup_session(attempt_stub(), self.plan, "https://x/")
            self.assertEqual(rec.calls, [])

    def test_provider_errors_and_missing_session_url_become_provider_error(self):
        for kw in (dict(status=500), dict(status=200, payload={}), dict(raises=TimeoutError("x"))):
            p, _ = self.provider(**kw)
            with self.assertRaises(ProviderError):
                p.create_recurring_setup_session(attempt_stub(), self.plan, "https://x/")

    # ---- charging
    def test_charge_sends_the_token_agreement_and_a_valid_hash(self):
        p, rec = self.provider(payload={"status": "SUCCESS", "transactionId": "TX-1", "orderId": "O-1",
                                        "transactionResponseCode": "00"})
        result = p.charge_saved_agreement(attempt_stub(), "tok-123")
        method, url, headers, body, _ = rec.calls[0]
        self.assertEqual((method, url), ("POST", "https://test-fep.kashier.io/v3/orders"))
        expected_hash = k.order_hash("MID-1-1", "chk_abc", "1000", "EGP", "madar-sub-7", DOC_KEY)
        self.assertEqual(headers["Kashier-Hash"], expected_hash)
        self.assertEqual(body["paymentMethod"]["card"]["cardToken"], "tok-123")
        self.assertEqual(body["paymentMethod"]["card"]["agreement"], {"id": "agr-9"})
        self.assertEqual((body["interactionSource"], body["order"]["amount"]), ("CONTAUTH", 1000))
        self.assertEqual((result.outcome, result.provider_transaction_id), ("succeeded", "TX-1"))

    def test_charge_outcome_is_decided_by_status_not_by_http_success_or_event(self):
        for payload, expected in (({"status": "FAILURE"}, "failed"), ({"status": "PENDING"}, "pending"),
                                  ({"status": "SUCCESS"}, "succeeded"), ({"response": {"status": "FAILURE"}}, "failed"),
                                  ({}, "unknown"), ({"status": "weird"}, "unknown")):
            p, _ = self.provider(payload=payload)
            self.assertEqual(p.charge_saved_agreement(attempt_stub(), "t").outcome, expected, payload)

    def test_a_timeout_or_transport_error_on_a_charge_is_unknown_never_failed(self):
        for exc in (TimeoutError("slow"), ConnectionResetError("reset"), OSError("net")):
            p, _ = self.provider(raises=exc)
            self.assertEqual(p.charge_saved_agreement(attempt_stub(), "t").outcome, "unknown")

    def test_http_errors_on_a_charge_are_unknown_never_failed(self):
        """A 403 INVALID_HASH_CHECK is OUR bug, not the customer's card: it must not put a paying
        teacher into the failed-payment state. Reconciliation decides."""
        for status in (400, 401, 403, 404, 500, 502, 503):
            p, _ = self.provider(status=status, payload={"status": "FAILURE"})
            self.assertEqual(p.charge_saved_agreement(attempt_stub(), "t").outcome, "unknown", status)

    def test_an_incomplete_saved_agreement_sends_nothing(self):
        p, rec = self.provider()
        stub = attempt_stub()
        stub.subscription.active_agreement.kashier_agreement_id = None
        with self.assertRaises(ProviderError):
            p.charge_saved_agreement(stub, "tok")
        with self.assertRaises(ProviderError):
            p.charge_saved_agreement(attempt_stub(), "")
        self.assertEqual(rec.calls, [])

    # ---- lookup
    def test_lookup_reads_pay_transactions_of_the_exact_order_only(self):
        orders = {"data": [
            {"merchantOrderId": "chk_abc-OTHER", "transactions": [{"operation": "pay", "status": "SUCCESS"}]},
            {"merchantOrderId": "chk_abc", "orderId": "O-1", "transactions": [
                {"operation": "3dsecure_verify", "status": "SUCCESS"},
                {"operation": "pay", "status": "SUCCESS", "transactionId": "TX-9"}]},
        ]}
        p, rec = self.provider(payload=orders)
        status = p.lookup_order("chk_abc")
        self.assertEqual((status.outcome, status.provider_transaction_id, status.provider_order_id),
                         ("succeeded", "TX-9", "O-1"))
        self.assertIn("search=chk_abc", rec.calls[0][1])
        self.assertEqual(rec.calls[0][2], {"Authorization": "test-secret"})

    def test_lookup_outcomes(self):
        def run(txns):
            p, _ = self.provider(payload={"data": [{"merchantOrderId": "o", "transactions": txns}]})
            return p.lookup_order("o").outcome
        self.assertEqual(run([{"operation": "pay", "status": "FAILURE"}]), "failed")
        self.assertEqual(run([{"operation": "pay", "status": "PENDING"}]), "pending")
        self.assertEqual(run([{"operation": "pay", "status": "FAILURE"}, {"operation": "pay", "status": "SUCCESS"}]), "succeeded")
        self.assertEqual(run([{"operation": "3dsecure_verify", "status": "SUCCESS"}]), "unknown")
        self.assertEqual(run([]), "unknown")

    def test_lookup_with_no_order_or_an_error_is_inconclusive(self):
        p, _ = self.provider(payload={"data": []})
        self.assertEqual(p.lookup_order("o").outcome, "unknown")
        p, _ = self.provider(status=500)
        self.assertEqual(p.lookup_order("o").outcome, "unknown")


@override_settings(**CONFIG)
class SafetyRailTests(SimpleTestCase):
    def test_no_outbound_call_is_ever_made_inside_a_transaction(self):
        rec = Recorder(payload={"status": "SUCCESS"})
        p = KashierProvider(transport=rec)
        with mock.patch("billing.providers.kashier.connection", mock.Mock(in_atomic_block=True)):
            with self.assertRaises(ProviderError):
                p.create_recurring_setup_session(attempt_stub(), SimpleNamespace(name="x"), "https://x/")
            self.assertEqual(p.charge_saved_agreement(attempt_stub(), "t").outcome, "unknown")
            with self.assertRaises(ProviderError):
                p.lookup_order("o")
        self.assertEqual(rec.calls, [], "the transport must not even be reached")

    def test_plain_http_provider_urls_are_refused(self):
        with override_settings(KASHIER_API_BASE_TEST="http://test-api.kashier.io"), \
                mock.patch("billing.providers.kashier.connection", mock.Mock(in_atomic_block=False)):
            rec = Recorder()
            with self.assertRaises(ProviderError):
                KashierProvider(transport=rec).lookup_order("o")
            self.assertEqual(rec.calls, [])

    def test_missing_keys_fail_closed(self):
        with override_settings(KASHIER_PAYMENT_API_KEY_TEST=""):
            body, headers = webhook(DOC_DATA)
            with self.assertRaises(InvalidSignature):
                KashierProvider().verify_and_parse_webhook(body, headers)

    def test_the_factory_returns_the_kashier_adapter(self):
        self.assertIsInstance(get_payment_provider(), KashierProvider)
        with override_settings(PAYMENT_PROVIDER="nope"):
            with self.assertRaises(ProviderError):
                get_payment_provider()

    def test_exceptions_never_contain_secrets(self):
        rec = Recorder(raises=OSError("boom"))
        with mock.patch("billing.providers.kashier.connection", mock.Mock(in_atomic_block=False)):
            try:
                KashierProvider(transport=rec).lookup_order("o")
            except ProviderError as exc:
                self.assertNotIn("test-secret", str(exc))
                self.assertNotIn(DOC_KEY, str(exc))
