"""
BILL-WU-035 — the one redaction policy for billing. Generalizes
`webhooks.py`'s own minimal card-shaped-key stripping (that unit's own
disclosed scope: "the full redaction policy is BILL-WU-035's job") into
a single helper every billing log line and the stored webhook payload
go through.

Two treatments, by key:
- Full redaction (`<redacted>`): cardholder name, masked/raw card
  fields, CVV/PAN, opaque tokens, and any literal secret/password/API
  key shaped field.
- Last-4-only masking: an agreement id (this unit's own wording:
  "agreement id (last 4 only)") — enough to recognize a value in a log
  without exposing it whole.

Key matching is case/separator-insensitive (`Card-Holder_Name` and
`cardHolderName` match the same rule) so a differently-cased provider
field never slips through.
"""

_FULL_REDACT_KEYS = frozenset({
    "card", "cardinfo", "cardnumber", "cardholdername", "maskedcard", "maskedpan",
    "cvv", "cvc", "pan", "token", "cardtoken", "secret", "secretkey", "apikey", "password", "signature",
})

_LAST4_ONLY_KEYS = frozenset({
    "agreementid", "agreementref", "kashieragreementid",
})

REDACTED = "<redacted>"


def _normalize(key):
    return str(key).lower().replace("_", "").replace("-", "")


def mask_last4(value):
    """Keep only the last 4 characters of `value`, masking the rest.
    A value of 4 characters or fewer is masked entirely (never reveals
    the whole thing just because it happened to be short)."""
    if value is None:
        return value
    text = str(value)
    if len(text) <= 4:
        return "*" * len(text)
    return "*" * (len(text) - 4) + text[-4:]


def redact_mapping(value):
    """Recursively walk `value` (dict/list/scalar); any dict key whose
    normalized form matches a known secret/card-data shape is replaced
    per its treatment above. Everything else passes through unchanged."""
    if isinstance(value, dict):
        result = {}
        for k, v in value.items():
            normalized = _normalize(k)
            if normalized in _FULL_REDACT_KEYS:
                result[k] = REDACTED
            elif normalized in _LAST4_ONLY_KEYS:
                result[k] = mask_last4(v)
            else:
                result[k] = redact_mapping(v)
        return result
    if isinstance(value, list):
        return [redact_mapping(v) for v in value]
    return value
