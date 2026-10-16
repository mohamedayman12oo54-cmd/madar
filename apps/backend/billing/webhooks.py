"""
BILL-WU-020 — the one ADR-016-approved inbound integration: Kashier's
payment-result webhook. Verifies the HMAC signature on the RAW request
body before trusting any byte, records the event durably exactly once
(dedup at the DB level), and acknowledges fast. **Applying** the verified
event to Subscription/PaymentAttempt/entitlement state is a separate step
(BILL-WU-021, out of scope here, per this unit's own exclusions) — so this
view never attempts it, and the event is always left `received`.

JWT does not apply: Kashier is not a Madar user. The HMAC signature IS the
authentication (ADR-016 prerequisite 1 — "an unverified request is never
processed"). This is the only `AllowAny` route `billing` adds.
"""
import hashlib

from django.conf import settings
from django.db import IntegrityError, transaction
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import audit
from .models import ProviderEvent
from .providers import InvalidSignature, get_payment_provider
from .redaction import redact_mapping

# A webhook payload is a small JSON document, never a file — this cap is
# far below DATA_UPLOAD_MAX_MEMORY_SIZE's bulk-upload ceiling (that
# setting governs ordinary request bodies; it is not reused or relied on
# here, since AllowAny + unauthenticated means this body is parsed before
# any of the usual request-size assumptions apply).
MAX_BODY_BYTES = 64 * 1024

# BILL-WU-035: `redacted_payload` is now stripped/masked by the canonical
# `redaction.redact_mapping` (cardholder name, masked card, tokens,
# secrets, agreement ids) rather than this unit's own original
# card-shaped-key-only pass — this is that unit's own disclosed
# follow-up ("the full redaction policy is BILL-WU-035's job").
_redact = redact_mapping


def _dedup_key(event):
    # PROPOSED composition (BILL-EXT-03 confirms the exact fields):
    # sha256(mode | provider transaction/order id | status | kind),
    # falling back from the provider transaction id to the provider order
    # id and finally to Madar's own merchant order id when the provider
    # hasn't assigned either yet.
    basis = event.provider_transaction_id or event.provider_order_id or event.merchant_order_id
    raw = f"{event.mode}|{basis}|{event.outcome_status}|{event.kind}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class KashierWebhookView(APIView):
    """POST /api/v1/billing/webhooks/kashier/"""

    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        raw_body = request.body
        if len(raw_body) > MAX_BODY_BYTES:
            return Response(status=400)

        provider = get_payment_provider()
        try:
            event = provider.verify_and_parse_webhook(raw_body, request.headers)
        except InvalidSignature:
            # ADR-016 prerequisite 1: nothing is persisted, and the
            # payload is never used for anything once verification fails.
            # "rejected (no body)": the raw/parsed payload is never a
            # field in this log line.
            audit.log("webhook_rejected", reason="invalid_signature")
            return Response(status=400)

        if event.mode != settings.KASHIER_MODE:
            # A signature that verified under the wrong mode's key (or a
            # payload that simply claims the wrong mode) must never be
            # accepted as if it matched this deployment's configuration.
            audit.log("webhook_rejected", reason="mode_mismatch", mode=event.mode)
            return Response(status=400)

        audit.log("webhook_verified", kind=event.kind, mode=event.mode)

        dedup_key = _dedup_key(event)
        try:
            with transaction.atomic():
                ProviderEvent.objects.create(
                    dedup_key=dedup_key,
                    mode=event.mode,
                    event_type=event.kind,
                    transaction_status=event.outcome_status,
                    provider_transaction_id=event.provider_transaction_id,
                    provider_order_id=event.provider_order_id,
                    signature_valid=True,
                    redacted_payload=_redact(event.raw),
                )
        except IntegrityError:
            # The same event delivered again (ADR-017 dedup, not the AI
            # idempotency_key mechanism) — already recorded; do nothing
            # else, and change no billing state.
            audit.log("webhook_duplicate", dedup_key=dedup_key)
            return Response(status=409)

        audit.log("webhook_received", dedup_key=dedup_key, kind=event.kind)

        # Acknowledge fast: respond only after the receipt commits. No
        # application attempt happens here (explicitly out of scope;
        # BILL-WU-021 owns it) — the event stays `received` until then.
        return Response(status=200)
