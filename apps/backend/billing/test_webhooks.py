"""
BILL-WU-020 — Kashier webhook receipt: signature verification, raw body,
durable receipt, dedup.
"""
import os

from django.test import SimpleTestCase, TestCase

from .models import ProviderEvent
from .providers import FakePaymentProvider

WEBHOOK_URL = "/api/v1/billing/webhooks/kashier/"


def _post_raw(client, raw_body, headers):
    kwargs = {f"HTTP_{k.upper().replace('-', '_')}": v for k, v in headers.items()}
    return client.post(WEBHOOK_URL, data=raw_body, content_type="application/json", **kwargs)


def _payload(**overrides):
    base = {
        "kind": "charge", "outcome_status": "SUCCESS", "merchant_order_id": "chk_abc123",
        "provider_transaction_id": "txn-1", "provider_order_id": "ord-1",
        "amount_minor_units": 100000, "currency": "EGP", "mode": "test",
    }
    base.update(overrides)
    return base


class WebhookReceiptTests(TestCase):
    """AC-BILL-020-1."""

    def test_a_correctly_signed_fixture_is_stored_once_and_answered_200(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload())

        r = _post_raw(self.client, raw_body, headers)

        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 1)
        event = ProviderEvent.objects.get()
        # The fixture names no known attempt, so the best-effort in-request application records it
        # as uncorrelated (changes no state) — the receipt itself is what this test pins.
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.FAILED_TO_APPLY)
        self.assertTrue(event.last_error.startswith("uncorrelated"))
        self.assertTrue(event.signature_valid)
        self.assertEqual(event.provider_transaction_id, "txn-1")
        self.assertEqual(event.transaction_status, "SUCCESS")


class WebhookDedupTests(TestCase):
    """AC-BILL-020-2."""

    def test_the_identical_event_delivered_again_yields_no_new_row_and_409(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload())

        r1 = _post_raw(self.client, raw_body, headers)
        r2 = _post_raw(self.client, raw_body, headers)

        self.assertEqual(r1.status_code, 200, r1.content)
        self.assertEqual(r2.status_code, 409, r2.content)
        self.assertEqual(ProviderEvent.objects.count(), 1)

    def test_an_idempotency_replay_event_kind_is_handled_the_same_way(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload(kind="idempotency"))

        r1 = _post_raw(self.client, raw_body, headers)
        r2 = _post_raw(self.client, raw_body, headers)

        # Kashier's `event="idempotency"` is a REPLAY notification: a duplicate signal, never a new
        # event. Acknowledge with 409 (so Kashier stops retrying) and store/apply nothing.
        self.assertEqual((r1.status_code, r2.status_code), (409, 409))
        self.assertEqual(ProviderEvent.objects.count(), 0)


class WebhookRejectionTests(TestCase):
    """AC-BILL-020-3."""

    def test_a_wrong_signature_is_rejected(self):
        provider = FakePaymentProvider()
        raw_body, _ = provider.sign_fake_webhook(_payload())

        r = _post_raw(self.client, raw_body, {"X-Fake-Signature": "0" * 64})

        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 0)

    def test_a_missing_signature_header_is_rejected(self):
        provider = FakePaymentProvider()
        raw_body, _ = provider.sign_fake_webhook(_payload())

        r = _post_raw(self.client, raw_body, {})

        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 0)

    def test_a_tampered_body_is_rejected(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload())
        tampered = raw_body.replace(b"SUCCESS", b"FAILURE")  # same length, different content

        r = _post_raw(self.client, tampered, headers)

        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 0)

    def test_a_payload_claiming_the_other_mode_is_rejected(self):
        """Settings default `KASHIER_MODE=test` under the test runner — a
        payload claiming `mode=live` must never be accepted as if it
        matched this deployment's configuration, even if (as with the
        fake provider) the signature itself verifies."""
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload(mode="live"))

        r = _post_raw(self.client, raw_body, headers)

        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 0)


class WebhookAuthenticationBypassTests(TestCase):
    """AC-BILL-020-4."""

    def test_works_without_any_authorization_header(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload())

        r = _post_raw(self.client, raw_body, headers)

        self.assertEqual(r.status_code, 200, r.content)

    def test_a_valid_jwt_with_no_signature_is_still_rejected(self):
        from accounts.models import User
        from rest_framework_simplejwt.tokens import RefreshToken

        user = User.objects.create_user(
            role=User.Role.TEACHER, name="t", email="wh-020@example.com", phone="201020000055",
            password="Str0ng!Pass", is_active=True,
        )
        access = str(RefreshToken.for_user(user).access_token)

        provider = FakePaymentProvider()
        raw_body, _ = provider.sign_fake_webhook(_payload())  # no signature header sent

        r = self.client.post(
            WEBHOOK_URL, data=raw_body, content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {access}"
        )

        self.assertEqual(r.status_code, 400, r.content)
        self.assertEqual(ProviderEvent.objects.count(), 0)


class NoAIIdempotencyReuseTests(SimpleTestCase):
    """AC-BILL-020-5: the AI `idempotency_key` mechanism is untouched and
    unused by billing CODE (ADR-017 — provider-event dedup is a separate
    mechanism). AST-based, not a text grep: `models.py` and `capabilities.py`
    (already VERIFIED, earlier units) legitimately *name* `AIOperation`/
    `idempotency_key` in prose docstrings to document the boundary this AC
    exists to protect — a plain substring search would flag that
    documentation as if it were a code dependency. Comments and docstrings
    never produce `Name`/`Attribute`/`Import` nodes, so this check is blind
    to prose and only catches an actual reference in code."""

    def test_billing_never_references_aioperation_or_idempotency_key(self):
        import ast

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
                    if isinstance(node, ast.Name) and node.id == "AIOperation":
                        offending.append(f"{path}: references AIOperation")
                    elif isinstance(node, ast.Attribute) and node.attr in ("AIOperation", "idempotency_key"):
                        offending.append(f"{path}: references .{node.attr}")
                    elif isinstance(node, (ast.Import, ast.ImportFrom)):
                        if any(alias.name == "AIOperation" for alias in node.names):
                            offending.append(f"{path}: imports AIOperation")
        self.assertEqual(offending, [], f"forbidden AIOperation/idempotency_key reference(s): {offending}")


class AllowAnyRouteEnumerationTests(SimpleTestCase):
    """AC-BILL-020-6: the URL table gains exactly one new `AllowAny`
    inbound route. Walks the real URL resolver (not a grep) so the result
    reflects actual runtime `permission_classes`, including any inherited
    from a base view. (`ThrottledTokenRefreshView` <- simplejwt's
    `TokenRefreshView` is pre-existing and effectively open too, via an
    *empty* `permission_classes` tuple rather than the `AllowAny` class —
    a different, already-existing mechanism this unit doesn't touch, so
    it's deliberately not in this literal-`AllowAny` set.) A future
    unrelated change that adds a new `AllowAny` view anywhere in the
    project will fail this test loudly — that is the point (ADR-016's
    "no precedent")."""

    EXPECTED = frozenset({
        "accounts.views.TeamLoginView",
        "accounts.views.TeacherLoginView",
        "accounts.views.StudentLoginView",
        "accounts.views.TeacherSignupStartView",
        "accounts.views.TeacherSignupEnvironmentView",
        "accounts.views.TeacherForgotRequestView",
        "accounts.views.TeacherForgotResetView",
        "accounts.views.StudentClaimRequestView",
        "accounts.views.StudentClaimActivateView",
        "accounts.views.StudentForgotRequestView",
        "accounts.views.StudentForgotResetView",
        "accounts.views.OTPVerifyView",
        "accounts.views.OTPResendView",
        "accounts.views.LogoutView",
        "parents.views.GuardianRequestView",
        "parents.views.GuardianCodeLoginView",
        "parents.views.GuardianVerifyView",
        "content.video_views.VideoStreamView",
        "billing.webhooks.KashierWebhookView",
        # Student self check-in (QR token + phone + announced code); attendance-only, throttled.
        "scheduling.checkin.CheckinInfoView",
        "scheduling.checkin.CheckinSubmitView",
        # Student self-registration (QR token): can only create an enrolment in its own environment.
        "academics.registration.RegistrationInfoView",
        "academics.registration.RegistrationSubmitView",
    })

    def test_the_allow_any_route_set_is_exactly_the_expected_one(self):
        from django.urls import get_resolver
        from rest_framework.permissions import AllowAny

        def iter_view_classes(resolver):
            for pattern in resolver.url_patterns:
                if hasattr(pattern, "url_patterns"):
                    yield from iter_view_classes(pattern)
                else:
                    view_class = getattr(pattern.callback, "view_class", None)
                    if view_class is not None:
                        yield view_class

        found = set()
        for view_class in iter_view_classes(get_resolver()):
            permission_classes = getattr(view_class, "permission_classes", ())
            if AllowAny in permission_classes:
                found.add(f"{view_class.__module__}.{view_class.__qualname__}")

        self.assertEqual(found, self.EXPECTED)


class WebhookReceiptCommitOrderingTests(TestCase):
    """AC-BILL-020-7: receipt commits before any state application. This
    unit's own "Explicit exclusions" forbid implementing state transitions
    (BILL-WU-021's job) — so no application attempt exists here at all,
    and the event is always left `received` with a 200 response. (A
    forced APPLICATION failure cannot yet be exercised meaningfully: there
    is no application step for it to interrupt until BILL-WU-021 exists.
    This test documents and locks in that current, correctly-scoped
    behaviour rather than inventing an application step prematurely.)"""

    def test_a_stored_event_is_left_received_and_the_response_is_200(self):
        provider = FakePaymentProvider()
        raw_body, headers = provider.sign_fake_webhook(_payload())

        from unittest import mock

        # AC-BILL-020-7: a forced application failure still answers 200 and leaves the event
        # `received`, so `process_billing_events` can recover it.
        with mock.patch("billing.events.apply", side_effect=RuntimeError("boom")):
            r = _post_raw(self.client, raw_body, headers)

        self.assertEqual(r.status_code, 200, r.content)
        event = ProviderEvent.objects.get()
        self.assertEqual(event.processing_status, ProviderEvent.ProcessingStatus.RECEIVED)
        self.assertEqual(event.attempts_count, 0)
        self.assertEqual(event.last_error, "")
