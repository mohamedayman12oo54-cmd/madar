"""Shared, secret-free fixtures for payment tests (kept out of any module named for the provider so the
"no provider import outside the adapter" static test stays meaningful)."""
DOC_KEY = "11111"   # the illustrative key used in the provider's own published examples
CONFIG = dict(
    PAYMENT_PROVIDER="kashier", KASHIER_MODE="test", KASHIER_MERCHANT_ID="MID-1-1",
    KASHIER_PAYMENT_API_KEY_TEST=DOC_KEY, KASHIER_PAYMENT_API_KEY_LIVE="live-payment-key",
    KASHIER_SECRET_KEY_TEST="test-secret", KASHIER_SECRET_KEY_LIVE="live-secret",
    KASHIER_WEBHOOK_URL="https://api.example.com/api/v1/billing/webhooks/kashier/",
    KASHIER_AGREEMENT_TYPE="RECURRING", KASHIER_AGREEMENT_PAYMENT_FREQUENCY="MONTHLY",
    KASHIER_AGREEMENT_MIN_DAYS_BETWEEN="25", KASHIER_AGREEMENT_EXPIRY_DATE="2030-01-01",
    KASHIER_AGREEMENT_NUMBER_OF_PAYMENTS="60",
)
