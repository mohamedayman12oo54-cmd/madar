"""
BILL-WU-018 — the Kashier adapter (ADR-015 concerns 3 and 4).

Every Kashier-specific fact lives in THIS file and nowhere else. Facts come
from Kashier's public developer docs (webhooks, recurring payments, request
hashing, order reconciliation — reviewed 2026-10-20). They are NOT contracts:
each one must be confirmed in the sandbox (BILL-WU-036 / BILL-EXT-03).

Security posture (the reason this file is paranoid):

* Webhook authenticity is a keyed HMAC over the fields named in the payload's
  own ``signatureKeys``. Because an attacker who replays an old signed event
  could otherwise edit any field NOT covered by that list, we additionally
  REQUIRE the list to cover every field we act on (``REQUIRED_SIGNED_KEYS``).
* Comparison is constant-time (``hmac.compare_digest``).
* The mode-specific Payment API Key is used, so a test-mode signature can
  never validate in live mode and vice versa.
* A transport timeout/5xx/4xx on a CHARGE is ``unknown`` — never ``failed``
  (a charge may or may not have happened; reconciliation decides).
* No outbound call may run inside a DB transaction (directive 15).
* Secrets, tokens and card data are never logged or put in exceptions.
"""
import hashlib
import hmac
import json
import urllib.error
import urllib.request
from decimal import Decimal, InvalidOperation
from urllib.parse import quote, urlparse

from django.conf import settings
from django.db import connection
from django.utils import timezone

from billing.providers import (
    ChargeResult, CheckoutSession, InvalidSignature, OrderStatus, PaymentProvider, ProviderError, VerifiedEvent,
)

HTTP_TIMEOUT_SECONDS = 20

# Fields we act on. Kashier's documented example covers all of them; if a
# payload's signatureKeys omits any, an attacker could tamper with it, so the
# event is rejected rather than trusted.
REQUIRED_SIGNED_KEYS = frozenset({"amount", "currency", "merchantOrderId", "status", "transactionId"})

_TOKEN_KEYS = ("cardDataToken", "cardToken")          # the docs are inconsistent; accept both
_AGREEMENT_KEYS = ("agreementId",)
_SEARCH_CONTAINERS = ("card", "cardInfo", "sourceOfFunds", "agreement", "paymentMethod")


# ------------------------------------------------------------- hashing ----
def encode_value(value):
    """URL-encode ONE value the way Kashier's docs require (RFC 3986,
    equivalent to strict-uri-encode / PHP_QUERY_RFC3986)."""
    if isinstance(value, bool):
        text = "true" if value else "false"
    elif value is None:
        text = ""
    else:
        text = str(value)
    return quote(text, safe="")


def webhook_signature(data, key):
    """HMAC-SHA256 hex of the sorted ``signatureKeys`` fields of ``data``."""
    keys = sorted(data["signatureKeys"])
    payload = "&".join(f"{k}={encode_value(data[k])}" for k in keys)
    return hmac.new(key.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()


def order_hash(merchant_id, reference, amount_text, currency, customer_reference, key):
    """The ``Kashier-Hash`` header. ``customerReference`` is mandatory
    whenever a token/agreement is sent (docs: otherwise 403 INVALID_HASH_CHECK)."""
    path = f"/?payment={merchant_id}.{reference}.{amount_text}.{currency}"
    if customer_reference:
        path += f".{customer_reference}"
    return hmac.new(key.encode("utf-8"), path.encode("utf-8"), hashlib.sha256).hexdigest()


def amount_text(minor_units):
    """Major-unit amount as Kashier signs/sends it: ``20.00`` -> ``20``."""
    major = Decimal(int(minor_units)) / Decimal(100)
    return format(major.normalize(), "f")


def _json_amount(minor_units):
    major = Decimal(int(minor_units)) / Decimal(100)
    return int(major) if major == major.to_integral_value() else float(major)


def minor_units_from(amount):
    """Kashier amounts are major units (EGP). Reject anything that is not an
    exact number of piastres instead of rounding money silently."""
    try:
        minor = Decimal(str(amount)) * Decimal(100)
    except (InvalidOperation, ValueError):
        raise ValueError("amount is not a number")
    if minor != minor.to_integral_value() or minor < 0:
        raise ValueError("amount is not an exact, non-negative number of piastres")
    return int(minor)


def customer_reference_for(subscription_id):
    return f"madar-sub-{subscription_id}"


# ------------------------------------------------------------ transport ----
def default_transport(method, url, headers, body, timeout):
    if urlparse(url).scheme != "https":  # defence in depth: file:/ftp:/custom schemes can never be opened here
        raise ProviderError("payment provider URLs must be https")
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310  # nosec B310 - https enforced above
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()


class KashierProvider(PaymentProvider):
    def __init__(self, transport=None):
        self._transport = transport or default_transport

    def ready_for_webhooks(self):
        try:
            self._payment_key()
        except ProviderError:
            return False
        return True

    # -------------------------------------------------------- settings ----
    @property
    def mode(self):
        return settings.KASHIER_MODE

    def _live(self):
        return self.mode == "live"

    def _payment_key(self):
        key = settings.KASHIER_PAYMENT_API_KEY_LIVE if self._live() else settings.KASHIER_PAYMENT_API_KEY_TEST
        if not key:
            raise ProviderError("Kashier payment API key is not configured for this mode.")
        return key

    def _secret_key(self):
        key = settings.KASHIER_SECRET_KEY_LIVE if self._live() else settings.KASHIER_SECRET_KEY_TEST
        if not key:
            raise ProviderError("Kashier secret key is not configured for this mode.")
        return key

    def _merchant_id(self):
        if not settings.KASHIER_MERCHANT_ID:
            raise ProviderError("KASHIER_MERCHANT_ID is not configured.")
        return settings.KASHIER_MERCHANT_ID

    def _api_base(self):
        return (settings.KASHIER_API_BASE_LIVE if self._live() else settings.KASHIER_API_BASE_TEST).rstrip("/")

    def _fep_base(self):
        base = settings.KASHIER_FEP_BASE_LIVE if self._live() else settings.KASHIER_FEP_BASE_TEST
        return base.rstrip("/")

    def _agreement(self):
        """BILL-EXT-01: the cadence parameters are configuration, never
        defaulted (a wrong guess would charge on the wrong schedule)."""
        values = {
            "type": settings.KASHIER_AGREEMENT_TYPE,
            "paymentFrequency": settings.KASHIER_AGREEMENT_PAYMENT_FREQUENCY,
            "minimumDaysBetweenPayments": settings.KASHIER_AGREEMENT_MIN_DAYS_BETWEEN,
            "expiryDate": settings.KASHIER_AGREEMENT_EXPIRY_DATE,
            "numberOfPayments": settings.KASHIER_AGREEMENT_NUMBER_OF_PAYMENTS,
        }
        missing = [k for k, v in values.items() if v in ("", None)]
        if missing:
            raise ProviderError(
                "Kashier agreement parameters are not configured (BILL-EXT-01): " + ", ".join(sorted(missing))
            )
        return {
            "type": values["type"],
            "amountVariability": "FIXED",
            "paymentFrequency": values["paymentFrequency"],
            "expiryDate": values["expiryDate"],
            "minimumDaysBetweenPayments": int(values["minimumDaysBetweenPayments"]),
            "numberOfPayments": int(values["numberOfPayments"]),
        }

    # ------------------------------------------------------------ http ----
    def _call(self, method, url, headers, payload=None):
        if connection.in_atomic_block:
            # Directive 15 / AC-BILL-018-5: never call out while a DB
            # transaction (and its row locks) is open.
            raise ProviderError("refusing an outbound payment call inside a database transaction")
        if urlparse(url).scheme != "https":
            raise ProviderError("payment provider URLs must be https")
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        try:
            status, raw = self._transport(method, url, headers, body, HTTP_TIMEOUT_SECONDS)
        except Exception:  # network error / timeout — details may contain URLs, never log them
            raise ProviderError("payment provider unreachable")
        try:
            parsed = json.loads(raw) if raw else {}
        except (ValueError, TypeError):
            parsed = {}
        return status, parsed

    # -------------------------------------------------------- checkout ----
    def create_recurring_setup_session(self, attempt, plan, return_url):
        if not settings.KASHIER_WEBHOOK_URL:
            raise ProviderError("KASHIER_WEBHOOK_URL is not configured.")
        agreement = self._agreement()
        body = {
            "expireAt": (timezone.now() + timezone.timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
            "maxFailureAttempts": 3,
            "paymentType": "credit",
            "amount": amount_text(attempt.amount_minor_units),
            "currency": attempt.currency,
            "merchantId": self._merchant_id(),
            "merchantOrderId": attempt.merchant_order_id,
            "merchantRedirect": return_url,
            "display": "ar",
            "type": "one-time",
            "allowedMethods": "card",
            "defaultMethod": "card",
            "description": f"Madar subscription - {plan.name}"[:120],
            "manualCapture": False,
            "customer": {"reference": customer_reference_for(attempt.subscription_id)},
            "agreement": agreement,
            "saveCard": "forced",
            "retrieveSavedCard": False,
            "interactionSource": "RECURRING",
            "enable3DS": True,
            "serverWebhook": settings.KASHIER_WEBHOOK_URL,
        }
        headers = {
            "Authorization": self._secret_key(), "api-key": self._payment_key(),
            "Content-Type": "application/json",
        }
        status, data = self._call("POST", f"{self._api_base()}/v3/payment/sessions", headers, body)
        session_url = data.get("sessionUrl") if isinstance(data, dict) else None
        if status >= 300 or not session_url:
            raise ProviderError("Kashier did not create a checkout session.")
        host = (urlparse(session_url).hostname or "").lower()
        if urlparse(session_url).scheme != "https" or not (host == "kashier.io" or host.endswith(".kashier.io")):
            # Never redirect a teacher's browser to a host we do not trust.
            raise ProviderError("Kashier returned an unexpected checkout URL.")
        return CheckoutSession(session_url=session_url, provider_session_ref=str(data.get("_id", ""))[:255])

    # ---------------------------------------------------------- charge ----
    def charge_saved_agreement(self, attempt, agreement_ref):
        agreement = getattr(attempt.subscription, "active_agreement", None)
        agreement_id = getattr(agreement, "kashier_agreement_id", None)
        if not agreement_ref or not agreement_id:
            # Nothing was sent, so nothing was charged: say so honestly.
            raise ProviderError("saved agreement is incomplete (token or agreement id missing)")
        customer_ref = customer_reference_for(attempt.subscription_id)
        mid = self._merchant_id()
        amt = amount_text(attempt.amount_minor_units)
        headers = {
            "Content-Type": "application/json",
            "Kashier-Hash": order_hash(mid, attempt.merchant_order_id, amt, attempt.currency, customer_ref,
                                       self._payment_key()),
        }
        empty_address = {k: None for k in ("city", "company", "country", "postcodeZip", "source",
                                           "stateProvince", "stateProvinceCode", "street", "street2")}
        body = {
            "apiOperation": "PAY",
            "paymentMethod": {"type": "CARD", "card": {
                "agreement": {"id": agreement_id}, "enable3DS": False, "cardToken": agreement_ref}},
            "order": {"reference": attempt.merchant_order_id, "amount": _json_amount(attempt.amount_minor_units),
                      "currency": attempt.currency},
            "shipping": {"address": {**empty_address, "sameAsBilling": True}, "method": "",
                         "origin": {"postcodeZip": ""}},
            "billing": {"address": empty_address},
            "interactionSource": "CONTAUTH",
            "reconciliation": {"webhookUrl": settings.KASHIER_WEBHOOK_URL,
                               "merchantRedirect": settings.KASHIER_WEBHOOK_URL},
            "merchantId": mid,
            "customer": {"reference": customer_ref},
        }
        try:
            status, data = self._call("POST", f"{self._fep_base()}/v3/orders", headers, body)
        except ProviderError:
            # Transport trouble after we may have sent the charge: AMBIGUOUS.
            return ChargeResult(outcome="unknown", raw_code="transport")
        outcome = _status_to_outcome(_find_status(data)) if 200 <= status < 300 else "unknown"
        return ChargeResult(
            outcome=outcome, provider_transaction_id=str(_find(data, ("transactionId",)) or "")[:255],
            provider_order_id=str(_find(data, ("orderId", "kashierOrderId")) or "")[:255],
            raw_code=str(_find(data, ("transactionResponseCode",)) or f"http{status}")[:64],
        )

    # --------------------------------------------------------- lookup ----
    def lookup_order(self, merchant_order_id):
        url = f"{self._api_base()}/v3/payment/orders?search={quote(merchant_order_id, safe='')}"
        status, data = self._call("GET", url, {"Authorization": self._secret_key()})
        if status >= 300 or not isinstance(data, dict):
            return OrderStatus(outcome="unknown", raw_code=f"http{status}")
        orders = [o for o in (data.get("data") or []) if isinstance(o, dict) and o.get("merchantOrderId") == merchant_order_id]
        if not orders:
            return OrderStatus(outcome="unknown", raw_code="not_found")
        outcomes, txn_id, order_id = [], "", ""
        for order in orders:
            order_id = order_id or str(order.get("orderId", ""))
            for txn in order.get("transactions") or []:
                if isinstance(txn, dict) and txn.get("operation") == "pay":
                    outcomes.append(_status_to_outcome(txn.get("status")))
                    if txn.get("status") == "SUCCESS":
                        txn_id = str(txn.get("transactionId", ""))
        if "succeeded" in outcomes:
            outcome = "succeeded"
        elif "pending" in outcomes:
            outcome = "pending"
        elif outcomes and all(o == "failed" for o in outcomes):
            outcome = "failed"
        else:
            outcome = "unknown"
        return OrderStatus(outcome=outcome, provider_transaction_id=txn_id, provider_order_id=order_id, raw_code=outcome)

    # -------------------------------------------------------- webhook ----
    def verify_and_parse_webhook(self, raw_body, headers):
        signature = (headers.get("x-kashier-signature") or "").strip().lower()
        if not signature:
            raise InvalidSignature("missing signature header")
        try:
            envelope = json.loads(raw_body)
            data = envelope["data"]
            keys = data["signatureKeys"]
        except (ValueError, TypeError, KeyError):
            raise InvalidSignature("malformed webhook body")
        if not isinstance(data, dict) or not isinstance(keys, list) or not keys or not all(isinstance(k, str) for k in keys):
            raise InvalidSignature("malformed signatureKeys")
        if not REQUIRED_SIGNED_KEYS.issubset(keys) or not all(k in data for k in keys):
            # An event that does not sign the fields we act on could have them forged.
            raise InvalidSignature("signatureKeys does not cover the required fields")
        try:
            expected = webhook_signature(data, self._payment_key())
        except ProviderError:
            raise InvalidSignature("verification key unavailable")
        if not hmac.compare_digest(signature, expected):
            raise InvalidSignature("signature mismatch")

        # ---- only past this line is any field trusted ----
        try:
            minor = minor_units_from(data["amount"])
        except ValueError:
            raise InvalidSignature("amount is not an exact monetary value")
        status = str(data["status"]).upper()
        kind = str(envelope.get("event", "")).lower()
        token = _find(data, _TOKEN_KEYS) or ""
        agreement_id = _find(data, _AGREEMENT_KEYS) or ""
        claimed_mode = str(data.get("mode", self.mode)).lower()
        neutral = {
            "merchant_order_id": str(data["merchantOrderId"]), "amount_minor_units": minor,
            "currency": str(data["currency"]).upper(), "provider_transaction_id": str(data["transactionId"]),
            "event": kind, "status": status,
            "transaction_response_code": str(data.get("transactionResponseCode", "")),
            "data": {k: v for k, v in data.items() if k != "signatureKeys"},
        }
        return VerifiedEvent(
            dedup_key="", kind=kind, outcome_status=status, merchant_order_id=neutral["merchant_order_id"],
            provider_transaction_id=neutral["provider_transaction_id"],
            provider_order_id=str(data.get("kashierOrderId", "")),
            amount_minor_units=minor, currency=neutral["currency"], agreement_ref=str(agreement_id),
            card_token=str(token), mode=claimed_mode, raw=neutral,
        )


# ------------------------------------------------------------ helpers ----
def _find(data, names, _depth=0):
    """Defensive lookup of the first present key in ``names`` at the top level
    or inside the known containers (the docs place tokens inconsistently)."""
    if not isinstance(data, dict) or _depth > 3:
        return None
    for name in names:
        if data.get(name):
            return data[name]
    for container in _SEARCH_CONTAINERS + ("response", "data"):
        found = _find(data.get(container), names, _depth + 1)
        if found:
            return found
    return None


def _find_status(data):
    return _find(data, ("status",)) if isinstance(data, dict) else None


def _status_to_outcome(status):
    """Branch on the transaction STATUS only — never on ``event``."""
    return {"SUCCESS": "succeeded", "FAILURE": "failed", "PENDING": "pending"}.get(str(status).upper(), "unknown")
