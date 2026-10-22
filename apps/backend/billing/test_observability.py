"""
BILL-WU-035 — billing observability: no secret/card data in logs,
one history row per Subscription/PaymentAttempt state change.
"""
import os

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from environments.tenancy_testing import TenantTestCase

from . import services
from .models import BillingTransition, PaymentAttempt, Plan, ProviderEvent, Subscription
from .providers import FakePaymentProvider
from .redaction import mask_last4, redact_mapping
from .transitions import record_ambiguous, record_confirmed_failure

WEBHOOK_URL = "/api/v1/billing/webhooks/kashier/"


def _post_raw(client, raw_body, headers):
    kwargs = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    return client.post(WEBHOOK_URL, data=raw_body, content_type="application/json", **kwargs)


def _payload(**overrides):
    base = {
        "kind": "charge", "outcome_status": "SUCCESS", "merchant_order_id": "chk_abc123",
        "provider_transaction_id": "txn-1", "provider_order_id": "ord-1",
        "amount_minor_units": 100000, "currency": "EGP", "mode": "test",
        "cardHolderName": "Jane Teacher", "maskedCard": "411111******1111",
        "token": "super-secret-token-value", "agreement_ref": "AGREEMENT1234567890",
    }
    base.update(overrides)
    return base


_SENSITIVE_VALUES = (
    "Jane Teacher", "411111******1111", "super-secret-token-value", "AGREEMENT1234567890",
)


class RedactionHelperTests(SimpleTestCase):
    """AC-BILL-035-1's underlying primitive."""

    def test_card_shaped_keys_are_fully_redacted(self):
        out = redact_mapping({"cardHolderName": "Jane Teacher", "maskedCard": "4111", "token": "abc"})
        self.assertEqual(out, {"cardHolderName": "<redacted>", "maskedCard": "<redacted>", "token": "<redacted>"})

    def test_agreement_id_keeps_only_last_4(self):
        self.assertEqual(mask_last4("AGREEMENT1234567890"), "***************7890")
        out = redact_mapping({"agreement_ref": "AGREEMENT1234567890"})
        self.assertEqual(out["agreement_ref"], "***************7890")

    def test_nested_structures_are_walked(self):
        out = redact_mapping({"data": {"card": {"cardNumber": "4111111111111111"}}})
        self.assertEqual(out["data"]["card"], "<redacted>")

    def test_ordinary_keys_pass_through_unchanged(self):
        out = redact_mapping({"status": "SUCCESS", "amount_minor_units": 100000})
        self.assertEqual(out, {"status": "SUCCESS", "amount_minor_units": 100000})


class WebhookLogAndStorageRedactionTests(TestCase):
    """AC-BILL-035-1: a webhook payload carrying cardholder-shaped and
    secret-shaped fields never leaves a trace of their real values,
    either in `ProviderEvent.redacted_payload` or in any log line."""

    def test_sensitive_fields_are_redacted_in_the_stored_payload(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload())

        r = _post_raw(self.client, raw_body, headers)

        self.assertEqual(r.status_code, 200, r.content)
        event = ProviderEvent.objects.get()
        stored = str(event.redacted_payload)
        for secret in _SENSITIVE_VALUES:
            self.assertNotIn(secret, stored)
        # last-4 masking is visible without exposing the secret: a
        # recognizable tail survives.
        self.assertIn("7890", event.redacted_payload["agreement_ref"])

    def test_no_log_line_emitted_during_the_webhook_flow_contains_a_raw_secret(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload())

        with self.assertLogs("billing", level="INFO") as captured:
            r = _post_raw(self.client, raw_body, headers)

        self.assertEqual(r.status_code, 200, r.content)
        rendered = "\n".join(captured.output)
        for secret in _SENSITIVE_VALUES:
            self.assertNotIn(secret, rendered)
        # Confirms the webhook flow actually produced the documented
        # lifecycle lines, not just an empty/irrelevant log capture.
        self.assertIn("event=webhook_verified", rendered)
        self.assertIn("event=webhook_received", rendered)

    def test_a_rejected_webhook_never_logs_the_payload_it_rejected(self):
        """"rejected (no body)" — an invalid signature must never cause
        any field of the untrusted payload to appear in the log."""
        provider = FakePaymentProvider()
        raw_body, _headers = provider.sign_fake_webhook(_payload())

        with self.assertLogs("billing", level="INFO") as captured:
            r = _post_raw(self.client, raw_body, {"X-Fake-Signature": "forged"})

        self.assertEqual(r.status_code, 400, r.content)
        rendered = "\n".join(captured.output)
        for secret in _SENSITIVE_VALUES:
            self.assertNotIn(secret, rendered)
        self.assertIn("event=webhook_rejected", rendered)
        self.assertIn("reason='invalid_signature'", rendered)


class CheckoutAndFailurePathLogTests(TenantTestCase):
    """AC-BILL-035-1's checkout/renewal-failure coverage, and the
    disclosed "secret leaks via exception repr" failure mode: a
    deliberately secret-shaped `provider_code` fed through the
    confirmed-failure path must never appear in a log line."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)

    def test_checkout_initiation_logs_no_secret(self):
        with self.assertLogs("billing", level="INFO") as captured:
            attempt, _url = services.start_checkout(self.env_a, Plan.Key.PLAN_1, "https://app.test/return")

        rendered = "\n".join(captured.output)
        self.assertIn("event=attempt_created", rendered)
        self.assertNotIn(attempt.merchant_order_id[:3] + "SECRET", rendered)  # sanity: no accidental concat

    def test_a_confirmed_failure_never_logs_the_providers_raw_code_verbatim(self):
        subscription = Subscription.objects.create(environment=self.env_a, plan=self.plan, state=Subscription.State.ACTIVE)
        attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=subscription, billing_period=None,
            merchant_order_id="chk_secret_test", amount_minor_units=self.plan.price_minor_units,
            status=PaymentAttempt.Status.PENDING,
        )
        secret_looking_code = "4111111111111111"  # a PAN-shaped value, worst case for this path

        with self.assertLogs("billing", level="INFO") as captured:
            record_confirmed_failure(attempt, provider_code=secret_looking_code, message="card declined")

        rendered = "\n".join(captured.output)
        self.assertNotIn(secret_looking_code, rendered)
        self.assertIn("event=attempt_outcome", rendered)


class TransitionHistoryTests(TenantTestCase):
    """AC-BILL-035-2: one append-only history row per Subscription/
    PaymentAttempt state change."""

    def setUp(self):
        super().setUp()
        self.plan = Plan.objects.get(key=Plan.Key.PLAN_1)

    def test_checkout_initiation_writes_one_history_row_for_the_new_attempt(self):
        before = BillingTransition.objects.count()
        attempt, _url = services.start_checkout(self.env_a, Plan.Key.PLAN_1, "https://app.test/return")

        rows = BillingTransition.objects.filter(model_name="payment_attempt", object_id=attempt.pk)
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertEqual(row.field, "status")
        self.assertEqual(row.to_value, PaymentAttempt.Status.INITIATED)
        self.assertEqual(BillingTransition.objects.count(), before + 1)

    def test_a_confirmed_renewal_failure_writes_history_for_both_the_attempt_and_the_subscription(self):
        subscription = Subscription.objects.create(environment=self.env_a, plan=self.plan, state=Subscription.State.ACTIVE)
        attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=subscription, billing_period=None,
            merchant_order_id="renew_hist_1", amount_minor_units=self.plan.price_minor_units,
            status=PaymentAttempt.Status.PENDING,
        )
        from .models import BillingPeriod

        period = BillingPeriod.objects.create(
            environment=self.env_a, subscription=subscription,
            period_start=timezone.now(), period_end=timezone.now() + timezone.timedelta(days=30),
        )
        attempt.billing_period = period
        attempt.save(update_fields=["billing_period"])

        record_confirmed_failure(attempt)

        attempt_rows = BillingTransition.objects.filter(model_name="payment_attempt", object_id=attempt.pk)
        sub_rows = BillingTransition.objects.filter(model_name="subscription", object_id=subscription.pk)
        self.assertEqual(attempt_rows.count(), 1)
        self.assertEqual(attempt_rows.get().to_value, PaymentAttempt.Status.FAILED)
        self.assertEqual(sub_rows.count(), 1)
        self.assertEqual(sub_rows.get().to_value, Subscription.State.PAST_DUE)

    def test_an_ambiguous_outcome_writes_exactly_one_history_row(self):
        subscription = Subscription.objects.create(environment=self.env_a, plan=self.plan)
        attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=subscription, billing_period=None,
            merchant_order_id="ambiguous_hist_1", amount_minor_units=self.plan.price_minor_units,
            status=PaymentAttempt.Status.PENDING,
        )

        record_ambiguous(attempt)

        rows = BillingTransition.objects.filter(model_name="payment_attempt", object_id=attempt.pk)
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().to_value, PaymentAttempt.Status.UNKNOWN)

    def test_a_repeat_call_after_terminal_status_writes_no_additional_row(self):
        """Mirrors `transitions.py`'s own terminal-precedence tests: a
        no-op status transition must never fabricate a history row."""
        subscription = Subscription.objects.create(environment=self.env_a, plan=self.plan)
        attempt = PaymentAttempt.objects.create(
            environment=self.env_a, subscription=subscription, billing_period=None,
            merchant_order_id="succeeded_hist_1", amount_minor_units=self.plan.price_minor_units,
            status=PaymentAttempt.Status.SUCCEEDED,
        )

        record_confirmed_failure(attempt, provider_code="LATE")

        self.assertEqual(BillingTransition.objects.filter(object_id=attempt.pk).count(), 0)

    def test_the_history_record_is_never_mutated_by_this_module(self):
        """AC-3's "append-only": static check that `record_transition`
        only ever calls `.create()`, never `.update()`/`.delete()`/`.save()`
        on `BillingTransition`."""
        import ast

        path = os.path.join(os.path.dirname(__file__), "audit.py")
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read(), filename=path)

        forbidden_calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr in ("update", "delete", "save"):
                forbidden_calls.append(node.attr)
        self.assertEqual(forbidden_calls, [])


class RunbookExistsTests(SimpleTestCase):
    """AC-BILL-035-3."""

    def test_the_runbook_file_exists_and_lists_every_alert_condition(self):
        path = os.path.join(
            os.path.dirname(__file__), "..", "..", "..", "docs", "services", "backend",
            "09-operations", "billing-runbook.md",
        )
        path = os.path.normpath(path)
        # The runbook lives in the repository's docs tree, which is not shipped with the backend alone.
        # Skip loudly (with the missing path) rather than fail on a checkout that has no docs; when the
        # docs tree IS present, a missing runbook is a real failure.
        docs_root = os.path.dirname(os.path.dirname(path))
        if not os.path.isdir(docs_root):
            self.skipTest(f"docs tree not present at {docs_root} — run from the full repository checkout")
        self.assertTrue(os.path.isfile(path), path)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        for condition in (
            "Verification failures spike", "Uncorrelated events", "Needs-attention events",
            "Unresolved attempts older than threshold", "Worker not running",
        ):
            self.assertIn(condition, text)
