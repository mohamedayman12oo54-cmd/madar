"""
BILL-WU-018 — the Kashier adapter (ADR-015 concerns 3 and 4).

Every Kashier-specific fact lives in this file and nowhere else. Built from
Kashier's published docs (developers.kashier.io: recurring, hashing, webhooks,
webhook payloads, order reconciliation). What the docs do NOT settle stays
defensive and is confirmed in sandbox (BILL-WU-036 / BILL-EXT-03):

  * anything that cannot be parsed with certainty maps to "unknown", never to
    "failed" or "succeeded" (a charge's outcome must be reconciled, not guessed);
  * a transport timeout during a charge is "unknown" (money may have moved);
  * the recurring agreement's cadence values come from configuration and are
    never defaulted to a calendar-month guess (BILL-EXT-01).

The adapter never persists anything and never sees a PAN/CVV. Secrets are
never placed in exceptions or logs.
"""
import hashlib
import hmac
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.utils import timezone

from .providers import (
    AgreementRef,
    ChargeResult,
    CheckoutSession,
    InvalidSignature,
    OrderStatus,
    PaymentProvider,
    ProviderError,
    VerifiedEvent,
    customer_reference_for,
)

HTTP_TIMEOUT_SECONDS = 15
SIGNATURE_HEADER = "x-kashier-signature"

# A signed webhook that does not sign these fields could carry unsigned values
# we would then act on — so their absence from `signatureKeys` is a rejection.
REQUIRED_SIGNED_KEYS = frozenset({"merchantOrderId", "status", "amount", "currency", "transactionId"})

# Minimal, non-personal subset of `data` kept for diagnostics. Everything else
# (merchantDetails, card.*, settlementInfo, platform, ...) is dropped on purpose.
_KEPT_DATA_KEYS = (
    "amount", "currency", "status", "method", "transactionId", "kashierOrderId", "orderReference",
    "transactionResponseCode", "creationDate", "channel",
)


class TransportTimeout(ProviderError):
    """The request may or may not have reached Kashier."""


def default_transport(method, url, headers, body, timeout):
    """stdlib HTTP (no extra dependency). Returns (status, body_bytes). HTTP
    error statuses are returned, not raised; network failure/timeouts raise."""
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 (https URLs only, see _url)
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise TransportTimeout("provider unreachable") from exc


def _money_str(minor_units):
    """Minor units (piasters) -> the major-unit number Kashier signs and
    expects, with no trailing zeros: 100000 -> '1000', 150050 -> '1500.5'."""
    major = (Decimal(int(minor_units)) / Decimal(100)).normalize()
    text = format(major, "f")
    return text


def _money_json(minor_units):
    text = _money_str(minor_units)
    return json.loads(text)  # int when integral, float otherwise (what the API example sends)


def _amount_to_minor(value):
    """Kashier amount (major units) -> integer minor units, or -1 when it is
    not an exact whole number of piasters (a sentinel that can never equal
    an attempt's expected amount, so the event is rejected as a mismatch)."""
    try:
        minor = Decimal(str(value)) * 100
    except (InvalidOperation, ValueError):
        return -1
    if minor != minor.to_integral_value() or minor < 0:
        return -1
    return int(minor)


def signature_payload(data):
    """The exact string Kashier signs (docs, 'Verify the signature'):
    keys from `signatureKeys`, sorted, each VALUE (only) URL-encoded, joined
    `k=v&k=v`. Raises InvalidSignature if it cannot be built unambiguously."""
    keys = data.get("signatureKeys")
    if not isinstance(keys, list) or not keys or not all(isinstance(k, str) for k in keys):
        raise InvalidSignature("signatureKeys missing")
    parts = []
    for key in sorted(keys):
        if key not in data:
            raise InvalidSignature("signed key absent")
        value = data[key]
        if isinstance(value, bool):
            text = "true" if value else "false"
        elif isinstance(value, float):
            text = str(int(value)) if value.is_integer() else repr(value)
        elif isinstance(value, (int, str)):
            text = str(value)
        else:  # None / list / dict are not representable unambiguously
            raise InvalidSignature("unsupported signed value")
        parts.append(f"{key}={urllib.parse.quote(text, safe='')}")
    return "&".join(parts)


class KashierPaymentProvider(PaymentProvider):
    def __init__(self, transport=None):
        self.mode = settings.KASHIER_MODE
        live = self.mode == "live"
        self.merchant_id = settings.KASHIER_MERCHANT_ID
        self.api_key = settings.KASHIER_PAYMENT_API_KEY_LIVE if live else settings.KASHIER_PAYMENT_API_KEY_TEST
        self.secret_key = settings.KASHIER_SECRET_KEY_LIVE if live else settings.KASHIER_SECRET_KEY_TEST
        self.api_base = (settings.KASHIER_API_BASE_LIVE if live else settings.KASHIER_API_BASE_TEST).rstrip("/")
        self.fep_base = (settings.KASHIER_FEP_BASE_LIVE if live else settings.KASHIER_FEP_BASE_TEST).rstrip("/")
        self._transport = transport or default_transport
        if not (self.merchant_id and self.api_key and self.secret_key):
            raise ProviderError("Kashier is not configured for the current mode")

    # ---- helpers -----------------------------------------------------------
    @staticmethod
    def customer_reference(attempt):
        return customer_reference_for(attempt)

    def _url(self, base, path):
        url = f"{base}{path}"
        if not url.startswith("https://"):
            raise ProviderError("provider URL must be https")
        return url

    def _hmac_hex(self, text):
        return hmac.new(self.api_key.encode("utf-8"), text.encode("utf-8"), hashlib.sha256).hexdigest()

    def order_hash(self, reference, amount_text, currency, customer_reference=""):
        path = f"/?payment={self.merchant_id}.{reference}.{amount_text}.{currency}"
        if customer_reference:
            path += f".{customer_reference}"
        return self._hmac_hex(path)

    def _json_call(self, method, url, headers, payload=None):
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        status, raw = self._transport(method, url, headers, body, HTTP_TIMEOUT_SECONDS)
        try:
            parsed = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            parsed = None
        return status, parsed

    def _agreement_settings(self):
        frequency = getattr(settings, "KASHIER_AGREEMENT_PAYMENT_FREQUENCY", "")
        min_days = getattr(settings, "KASHIER_AGREEMENT_MIN_DAYS_BETWEEN_PAYMENTS", 0)
        if not frequency or not min_days:
            # BILL-EXT-01: the cadence values are deliberately not defaulted.
            raise ProviderError("recurring agreement cadence is not configured (BILL-EXT-01)")
        return frequency, int(min_days)

    # ---- PaymentProvider ---------------------------------------------------
    def create_recurring_setup_session(self, attempt, plan, return_url):
        frequency, min_days = self._agreement_settings()
        webhook_url = getattr(settings, "KASHIER_WEBHOOK_URL", "")
        if not webhook_url.startswith("https://"):
            raise ProviderError("KASHIER_WEBHOOK_URL must be a public https URL")
        now = timezone.now()
        payload = {
            "expireAt": (now + timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "maxFailureAttempts": 3,
            "paymentType": "credit",
            "amount": _money_str(attempt.amount_minor_units),
            "currency": attempt.currency,
            "merchantId": self.merchant_id,
            "merchantOrderId": attempt.merchant_order_id,
            "merchantRedirect": return_url,
            "display": "ar",
            "type": "one-time",
            "allowedMethods": "card",
            "defaultMethod": "card",
            "failureRedirect": False,
            "description": f"Madar subscription - {plan.key}",
            "manualCapture": False,
            "customer": {"reference": self.customer_reference(attempt)},
            "agreement": {
                "type": "RECURRING",
                "amountVariability": getattr(settings, "KASHIER_AGREEMENT_AMOUNT_VARIABILITY", "VARIABLE"),
                "paymentFrequency": frequency,
                "minimumDaysBetweenPayments": min_days,
                "expiryDate": (now + timedelta(days=365 * int(getattr(settings, "KASHIER_AGREEMENT_YEARS", 10)))).strftime("%Y-%m-%d"),
                "maximumAmountPerPayment": int(getattr(settings, "KASHIER_AGREEMENT_MAX_AMOUNT", 5000)),
                "numberOfPayments": int(getattr(settings, "KASHIER_AGREEMENT_NUMBER_OF_PAYMENTS", 1200)),
            },
            "saveCard": "forced",
            "interactionSource": "RECURRING",
            "enable3DS": True,
            "serverWebhook": webhook_url,
        }
        headers = {"Authorization": self.secret_key, "api-key": self.api_key, "Content-Type": "application/json"}
        status, body = self._json_call("POST", self._url(self.api_base, "/v3/payment/sessions"), headers, payload)
        if status not in (200, 201) or not isinstance(body, dict):
            raise ProviderError(f"session creation rejected (HTTP {status})")
        session_url = body.get("sessionUrl") or ""
        host = urllib.parse.urlparse(session_url).hostname or ""
        if not session_url.startswith("https://") or not (host == "kashier.io" or host.endswith(".kashier.io")):
            # Never hand the browser a URL that is not Kashier's.
            raise ProviderError("provider returned an unexpected session URL")
        return CheckoutSession(session_url=session_url, provider_session_ref=str(body.get("_id", "")))

    def charge_saved_agreement(self, attempt, agreement_ref):
        token, _, agreement_id = (agreement_ref or "").partition("|")
        if not token or not agreement_id:
            raise ProviderError("stored agreement is incomplete")
        reference = attempt.merchant_order_id
        customer = self.customer_reference(attempt)
        webhook_url = getattr(settings, "KASHIER_WEBHOOK_URL", "")
        payload = {
            "apiOperation": "PAY",
            "paymentMethod": {"type": "CARD", "card": {
                "agreement": {"id": agreement_id}, "enable3DS": False, "cardToken": token,
            }},
            "order": {"reference": reference, "amount": _money_json(attempt.amount_minor_units),
                      "currency": attempt.currency},
            "interactionSource": "CONTAUTH",
            "reconciliation": {"webhookUrl": webhook_url} if webhook_url else {},
            "merchantId": self.merchant_id,
            "customer": {"reference": customer},
        }
        headers = {
            "Kashier-Hash": self.order_hash(reference, _money_str(attempt.amount_minor_units), attempt.currency, customer),
            "Content-Type": "application/json",
        }
        try:
            status, body = self._json_call("POST", self._url(self.fep_base, "/v3/orders"), headers, payload)
        except TransportTimeout:
            # Money may or may not have moved: ambiguous, never "failed".
            return ChargeResult(outcome="unknown", raw_code="transport")
        return self._charge_result(status, body)

    @staticmethod
    def _charge_result(status, body):
        if status >= 500 or not isinstance(body, dict):
            return ChargeResult(outcome="unknown", raw_code=f"http_{status}")
        container = body.get("response") if isinstance(body.get("response"), dict) else body
        raw_status = str(container.get("status") or container.get("transactionStatus") or body.get("status") or "").upper()
        txn = str(container.get("transactionId") or body.get("transactionId") or "")
        order = str(container.get("orderId") or body.get("orderId") or container.get("kashierOrderId") or "")
        code = str(container.get("transactionResponseCode") or body.get("transactionResponseCode") or "")
        if raw_status == "SUCCESS" and txn and status < 300:
            return ChargeResult("succeeded", provider_transaction_id=txn, provider_order_id=order, raw_code=code or "00")
        if raw_status == "FAILURE":
            return ChargeResult("failed", provider_transaction_id=txn, provider_order_id=order, raw_code=code or "failure")
        if raw_status == "PENDING":
            return ChargeResult("pending", provider_transaction_id=txn, provider_order_id=order, raw_code=code or "pending")
        # 4xx without a clear transaction verdict (e.g. 403 INVALID_HASH_CHECK)
        # or anything unparseable: not proof of success OR of failure.
        return ChargeResult(outcome="unknown", raw_code=f"http_{status}")

    def _find_order(self, merchant_order_id):
        headers = {"Authorization": self.secret_key}
        url = self._url(self.api_base, "/v3/payment/orders?" + urllib.parse.urlencode({"search": merchant_order_id}))
        status, body = self._json_call("GET", url, headers)
        if status != 200 or not isinstance(body, dict) or not isinstance(body.get("data"), list):
            return None
        # `search` is a case-insensitive PARTIAL match: only an exact id counts.
        matches = [o for o in body["data"] if isinstance(o, dict) and o.get("merchantOrderId") == merchant_order_id]
        return matches[0] if matches else None

    def lookup_order(self, merchant_order_id):
        try:
            order = self._find_order(merchant_order_id)
        except TransportTimeout:
            return OrderStatus(outcome="unknown", raw_code="transport")
        if order is None:
            return OrderStatus(outcome="unknown", raw_code="not_found")
        pays = [t for t in (order.get("transactions") or []) if isinstance(t, dict) and str(t.get("operation", "")).lower() == "pay"]
        if not pays:
            return OrderStatus(outcome="unknown", raw_code=str(order.get("status", "")), provider_order_id=str(order.get("orderId", "")))
        # Any successful pay transaction means the order was paid; otherwise judge by the latest.
        paid = next((t for t in pays if str(t.get("status", "")).upper() == "SUCCESS"), None)
        chosen = paid or pays[-1]
        verdict = str(chosen.get("status", "")).upper()
        outcome = {"SUCCESS": "succeeded", "FAILURE": "failed", "PENDING": "pending"}.get(verdict, "unknown")
        return OrderStatus(
            outcome=outcome, provider_transaction_id=str(chosen.get("transactionId", "")),
            provider_order_id=str(order.get("orderId", "")), raw_code=str(chosen.get("transactionResponseCode", "")),
        )

    def fetch_agreement(self, merchant_order_id, customer_reference=""):
        """The token/agreement for a paid setup order. Kashier's webhook payload
        does not reliably carry them (docs disagree, BILL-EXT-03), so they are
        read from Kashier directly: the order record first, then the token list."""
        try:
            order = self._find_order(merchant_order_id)
            if order:
                info = ((order.get("sourceOfFunds") or {}).get("cardInfo") or {})
                token = info.get("cardDataToken")
                agreement = info.get("agreement")
                agreement_id = agreement.get("id") if isinstance(agreement, dict) else agreement
                if token and agreement_id:
                    return AgreementRef(card_token=str(token), agreement_id=str(agreement_id))
            if customer_reference:
                url = self._url(self.api_base, "/v3/payment/tokenization/tokens?sortType=-1&page=1&limit=20")
                status, body = self._json_call("GET", url, {"Authorization": self.secret_key})
                if status == 200 and isinstance(body, dict):
                    for item in body.get("data") or []:
                        if isinstance(item, dict) and item.get("customerReference") == customer_reference \
                                and item.get("token") and item.get("agreementId"):
                            return AgreementRef(card_token=str(item["token"]), agreement_id=str(item["agreementId"]))
        except TransportTimeout:
            return None
        return None

    def verify_and_parse_webhook(self, raw_body, headers):
        received = (headers.get(SIGNATURE_HEADER) or headers.get("X-Kashier-Signature") or "").strip().lower()
        try:
            body = json.loads(raw_body)
            data = body["data"]
            event_name = str(body.get("event", ""))
            if not isinstance(data, dict):
                raise TypeError
        except (ValueError, TypeError, KeyError):
            raise InvalidSignature("malformed webhook body")
        expected = self._hmac_hex(signature_payload(data))
        if not received or not hmac.compare_digest(received, expected):
            raise InvalidSignature("signature mismatch")
        signed = set(data["signatureKeys"])
        if not REQUIRED_SIGNED_KEYS <= signed:
            raise InvalidSignature("required fields are not covered by the signature")

        status = str(data["status"]).upper()
        merchant_order_id = str(data["merchantOrderId"])
        transaction_id = str(data["transactionId"])
        amount_minor = _amount_to_minor(data["amount"])
        # A replayed notification (`idempotency`) is the same logical event.
        kind = "pay" if event_name == "idempotency" else event_name
        basis = f"{self.mode}|{transaction_id}|{status}|{kind}"
        normalized = {
            "event": event_name, "merchant_order_id": merchant_order_id,
            "amount_minor_units": amount_minor, "currency": str(data["currency"]),
            "agreement_ref": "",  # never taken from the webhook: fetched from Kashier at activation
            "data": {k: data[k] for k in _KEPT_DATA_KEYS if k in data},
        }
        return VerifiedEvent(
            dedup_key=hashlib.sha256(basis.encode("utf-8")).hexdigest(),
            kind=kind, outcome_status=status, merchant_order_id=merchant_order_id,
            provider_transaction_id=transaction_id, provider_order_id=str(data.get("kashierOrderId", "")),
            amount_minor_units=amount_minor, currency=str(data["currency"]), agreement_ref="",
            mode=self.mode, raw=normalized,
        )
