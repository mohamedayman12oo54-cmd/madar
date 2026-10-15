"""
BILL-WU-017 — payment-provider interface and fake-provider tests.
"""
import ast
import os

from django.test import SimpleTestCase, override_settings

from .providers import (
    ChargeResult,
    FakePaymentProvider,
    InvalidSignature,
    PaymentProvider,
    ProviderError,
    VerifiedEvent,
    get_payment_provider,
)


class _FakeAttempt:
    """Stand-in for a `billing.models.PaymentAttempt` row — the provider
    only ever reads `.merchant_order_id` from it."""

    def __init__(self, merchant_order_id):
        self.merchant_order_id = merchant_order_id


class FakeProviderWebhookSignatureTests(SimpleTestCase):
    """AC-BILL-017-2."""

    def setUp(self):
        self.provider = FakePaymentProvider()
        self.payload = {
            "kind": "charge", "outcome_status": "succeeded", "merchant_order_id": "order-1",
            "provider_transaction_id": "txn-1", "provider_order_id": "ord-1",
            "amount_minor_units": 100000, "currency": "EGP", "mode": "test",
        }

    def test_a_correctly_signed_webhook_is_accepted(self):
        raw_body, headers = self.provider.sign_fake_webhook(self.payload)
        event = self.provider.verify_and_parse_webhook(raw_body, headers)
        self.assertIsInstance(event, VerifiedEvent)
        self.assertEqual(event.merchant_order_id, "order-1")
        self.assertEqual(event.outcome_status, "succeeded")
        self.assertTrue(event.dedup_key)

    def test_a_tampered_body_is_rejected(self):
        raw_body, headers = self.provider.sign_fake_webhook(self.payload)
        tampered = raw_body.replace(b"succeeded", b"failed   ")  # same length, different content
        with self.assertRaises(InvalidSignature):
            self.provider.verify_and_parse_webhook(tampered, headers)

    def test_a_wrong_signature_is_rejected(self):
        raw_body, _ = self.provider.sign_fake_webhook(self.payload)
        with self.assertRaises(InvalidSignature):
            self.provider.verify_and_parse_webhook(raw_body, {"X-Fake-Signature": "0" * 64})

    def test_a_missing_signature_header_is_rejected(self):
        raw_body, _ = self.provider.sign_fake_webhook(self.payload)
        with self.assertRaises(InvalidSignature):
            self.provider.verify_and_parse_webhook(raw_body, {})


class FakeProviderScriptedOutcomeTests(SimpleTestCase):
    def test_default_outcome_is_succeeded(self):
        provider = FakePaymentProvider()
        result = provider.charge_saved_agreement(_FakeAttempt("order-x"), "agreement-ref")
        self.assertEqual(result.outcome, "succeeded")

    def test_scripted_outcome_is_honored(self):
        provider = FakePaymentProvider()
        provider.script_outcome("order-y", "failed")
        result = provider.charge_saved_agreement(_FakeAttempt("order-y"), "agreement-ref")
        self.assertEqual(result.outcome, "failed")

    def test_unscripted_orders_are_unaffected_by_other_scripted_orders(self):
        provider = FakePaymentProvider()
        provider.script_outcome("order-y", "failed")
        result = provider.charge_saved_agreement(_FakeAttempt("order-unrelated"), "agreement-ref")
        self.assertEqual(result.outcome, "succeeded")

    def test_unknown_scripted_outcome_is_rejected(self):
        provider = FakePaymentProvider()
        with self.assertRaises(ValueError):
            provider.script_outcome("order-z", "bogus")

    def test_lookup_order_honors_the_same_script(self):
        provider = FakePaymentProvider()
        provider.script_outcome("order-w", "pending")
        self.assertEqual(provider.lookup_order("order-w").outcome, "pending")


class CreateRecurringSetupSessionTests(SimpleTestCase):
    def test_returns_a_session_url_and_a_provider_ref(self):
        provider = FakePaymentProvider()
        session = provider.create_recurring_setup_session(
            _FakeAttempt("order-a"), plan=None, return_url="https://app.example.com/return"
        )
        self.assertTrue(session.session_url.startswith("https://fake-kashier.test/"))
        self.assertTrue(session.provider_session_ref)


class ChargeResultValidationTests(SimpleTestCase):
    def test_an_invalid_outcome_is_rejected_at_construction(self):
        with self.assertRaises(ValueError):
            ChargeResult(outcome="not-a-real-outcome")


class GetPaymentProviderFactoryTests(SimpleTestCase):
    """AC-BILL-017-1 (the public factory shape)."""

    def test_default_setting_returns_the_fake_provider(self):
        provider = get_payment_provider()
        self.assertIsInstance(provider, FakePaymentProvider)
        self.assertIsInstance(provider, PaymentProvider)

    def test_unknown_provider_name_raises_provider_error(self):
        with override_settings(PAYMENT_PROVIDER="not-a-real-provider"):
            with self.assertRaises(ProviderError):
                get_payment_provider()


class NoVideoProviderReuseTests(SimpleTestCase):
    """AC-BILL-017-6."""

    def test_no_billing_provider_class_subclasses_video_provider(self):
        from content.providers import VideoProvider

        for cls in (PaymentProvider, FakePaymentProvider):
            self.assertNotIn(VideoProvider, cls.__mro__, f"{cls.__name__} must not subclass VideoProvider")


class NoKashierImportOutsideAdapterTests(SimpleTestCase):
    """AC-BILL-017-1 (static half): nothing in `billing/` may import a
    concrete 'kashier' module. None exists yet (BILL-WU-018) — this is a
    regression guard for once one does: only the adapter package itself
    (`billing.providers.kashier*`) is allowed to name it."""

    ALLOWED_PREFIX = "billing.providers.kashier"

    def test_no_billing_module_imports_kashier_outside_the_adapter(self):
        billing_dir = os.path.dirname(__file__)
        offending = []
        for root, dirs, files in os.walk(billing_dir):
            dirs[:] = [d for d in dirs if d != "migrations"]
            for filename in files:
                if not filename.endswith(".py"):
                    continue
                path = os.path.join(root, filename)
                with open(path, encoding="utf-8") as fh:
                    tree = ast.parse(fh.read(), filename=path)
                for node in ast.walk(tree):
                    modules = []
                    if isinstance(node, ast.Import):
                        modules = [alias.name for alias in node.names]
                    elif isinstance(node, ast.ImportFrom) and node.module:
                        modules = [node.module]
                    for module in modules:
                        if "kashier" in module.lower() and not module.startswith(self.ALLOWED_PREFIX):
                            offending.append(f"{path}: imports {module!r}")
        self.assertEqual(offending, [], f"forbidden kashier import(s): {offending}")
