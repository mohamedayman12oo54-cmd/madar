"""
Madar-owned payment-provider interface (BILL-WU-017; ADR-015 concern 2),
kept separate from provider-neutral billing decisions (concern 1 —
`billing/entitlements.py`), the Kashier adapter (concern 3 — BILL-WU-018,
not built here), and inbound verification/translation (concern 4 —
consumed by BILL-WU-020).

Deliberately NOT a subclass of, and sharing no code with,
`content.providers.VideoProvider` (ADR-015 §Alternatives, this unit's own
escalation condition). That class's `verify_webhook` stub
(`content/providers.py:97-99`) just `return False` — a correct no-op for a
provider nothing external calls, but a dangerous one if ever reused for
payment events. See `verify_and_parse_webhook` below for what a real check
has to do instead.

The only implementation here is `FakePaymentProvider`. No Kashier
credentials exist anywhere in this project; the real adapter is a
separate, later unit (BILL-WU-018). `FakePaymentProvider` is
deterministic and scriptable, modeled on `ai.providers.StubTutorProvider`,
so every billing flow can be built and tested without network access or
real credentials.

The provider never persists anything (ADR-015 concern 5): it returns
results: billing services (BILL-WU-019/020/021/...) do the writes.
"""
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field


class ProviderError(RuntimeError):
    """Any provider-side failure that is not a signature problem (e.g. the
    provider is unreachable, or returns something Madar can't parse)."""


class InvalidSignature(RuntimeError):
    """Raised by `verify_and_parse_webhook` when the inbound request's
    signature does not match. The caller MUST NOT use the payload."""


@dataclass
class CheckoutSession:
    session_url: str
    provider_session_ref: str


@dataclass
class ChargeResult:
    OUTCOMES = ("succeeded", "failed", "pending", "unknown")

    outcome: str
    provider_transaction_id: str = ""
    provider_order_id: str = ""
    raw_code: str = ""

    def __post_init__(self):
        if self.outcome not in self.OUTCOMES:
            raise ValueError(f"unknown ChargeResult outcome {self.outcome!r}")


@dataclass
class OrderStatus:
    outcome: str
    provider_transaction_id: str = ""
    provider_order_id: str = ""
    raw_code: str = ""


@dataclass
class VerifiedEvent:
    """Provider-neutral shape a verified webhook is translated into. Past
    this point nothing downstream ever sees the raw Kashier payload
    (ADR-016/017) — only these named fields."""

    dedup_key: str
    kind: str
    outcome_status: str
    merchant_order_id: str
    provider_transaction_id: str = ""
    provider_order_id: str = ""
    amount_minor_units: int = 0
    currency: str = "EGP"
    agreement_ref: str = ""
    mode: str = "test"
    raw: dict = field(default_factory=dict)


class PaymentProvider:
    """Abstract contract. Method names are indicative, per this unit's own
    wording — the real adapter (BILL-WU-018) may need to adjust them, but
    callers depend only on this shape, never on a concrete provider."""

    def create_recurring_setup_session(self, attempt, plan, return_url) -> CheckoutSession:  # pragma: no cover - interface
        raise NotImplementedError

    def charge_saved_agreement(self, attempt, agreement_ref) -> ChargeResult:  # pragma: no cover - interface
        raise NotImplementedError

    def lookup_order(self, merchant_order_id) -> OrderStatus:  # pragma: no cover - interface
        raise NotImplementedError

    def verify_and_parse_webhook(self, raw_body: bytes, headers) -> VerifiedEvent:  # pragma: no cover - interface
        raise NotImplementedError


class FakePaymentProvider(PaymentProvider):
    """Deterministic, scriptable fake for tests and local development.

    `script_outcome(merchant_order_id, outcome)` controls what
    `charge_saved_agreement`/`lookup_order` return for that attempt;
    unscripted calls default to "succeeded" so a happy-path test needs no
    scripting at all.

    Fake webhooks are HMAC-signed with a fixed, non-secret test key (this
    is a fake — there is nothing real to protect) using
    `hmac.compare_digest`, the same constant-time comparison a real
    adapter must use, so a test exercising `verify_and_parse_webhook`
    exercises the actual comparison code path rather than a shortcut.
    """

    TEST_SIGNING_KEY = b"fake-provider-test-signing-key-not-a-secret"

    def __init__(self):
        self._scripted_outcomes = {}

    def script_outcome(self, merchant_order_id, outcome):
        if outcome not in ChargeResult.OUTCOMES:
            raise ValueError(f"unknown outcome {outcome!r}")
        self._scripted_outcomes[merchant_order_id] = outcome

    def create_recurring_setup_session(self, attempt, plan, return_url):
        ref = f"fake-session-{secrets.token_urlsafe(16)}"
        return CheckoutSession(
            session_url=f"https://fake-kashier.test/pay/{ref}?return_url={return_url}",
            provider_session_ref=ref,
        )

    def charge_saved_agreement(self, attempt, agreement_ref):
        outcome = self._scripted_outcomes.get(attempt.merchant_order_id, "succeeded")
        return ChargeResult(
            outcome=outcome,
            provider_transaction_id=f"fake-txn-{secrets.token_urlsafe(8)}",
            provider_order_id=f"fake-order-{secrets.token_urlsafe(8)}",
            raw_code="00" if outcome == "succeeded" else outcome,
        )

    def lookup_order(self, merchant_order_id):
        outcome = self._scripted_outcomes.get(merchant_order_id, "succeeded")
        return OrderStatus(outcome=outcome, raw_code="00" if outcome == "succeeded" else outcome)

    def sign_fake_webhook(self, payload: dict):
        """Build a `(raw_body, headers)` pair a test can hand straight to
        `verify_and_parse_webhook`."""
        raw_body = json.dumps(payload).encode("utf-8")
        signature = hmac.new(self.TEST_SIGNING_KEY, raw_body, hashlib.sha256).hexdigest()
        return raw_body, {"X-Fake-Signature": signature}

    def verify_and_parse_webhook(self, raw_body: bytes, headers) -> VerifiedEvent:
        signature = headers.get("X-Fake-Signature", "")
        expected = hmac.new(self.TEST_SIGNING_KEY, raw_body, hashlib.sha256).hexdigest()
        if not signature or not hmac.compare_digest(signature, expected):
            raise InvalidSignature("fake webhook signature mismatch")
        try:
            payload = json.loads(raw_body)
        except (ValueError, TypeError):
            raise InvalidSignature("fake webhook body is not valid JSON")
        return VerifiedEvent(
            dedup_key=(
                f"{payload.get('provider_transaction_id', '')}:"
                f"{payload.get('outcome_status', '')}:{payload.get('kind', '')}"
            ),
            kind=payload.get("kind", "charge"),
            outcome_status=payload.get("outcome_status", "unknown"),
            merchant_order_id=payload.get("merchant_order_id", ""),
            provider_transaction_id=payload.get("provider_transaction_id", ""),
            provider_order_id=payload.get("provider_order_id", ""),
            amount_minor_units=payload.get("amount_minor_units", 0),
            currency=payload.get("currency", "EGP"),
            agreement_ref=payload.get("agreement_ref", ""),
            mode=payload.get("mode", "test"),
            raw=payload,
        )


_PROVIDERS = {"fake": FakePaymentProvider}


def get_payment_provider() -> PaymentProvider:
    from django.conf import settings

    name = getattr(settings, "PAYMENT_PROVIDER", "fake")
    try:
        return _PROVIDERS[name]()
    except KeyError:
        raise ProviderError(
            f"PAYMENT_PROVIDER {name!r} is not implemented here. Available: {', '.join(_PROVIDERS)}."
        )
