# Billing (Kashier) observability runbook — BILL-WU-035

> **Open item carried forward (NODE-Vendors, this unit's own tracked open item):** no APM or
> error-tracking vendor is selected. Every alert below is a log-query or a direct database check
> against the `billing` logger / `BillingTransition` history table, not a paging integration.
> Selecting a vendor is explicitly out of scope for this unit.

## Where the signal lives

- **Logs:** the `billing` logger (`config/settings.py` `LOGGING["loggers"]["billing"]`), console
  handler, `INFO` level. Every line is `event=<label> k=v k=v ...`, written by
  `billing/audit.py`'s `log()` — the only place `billing/*` calls `logging.getLogger`. Fields are
  redacted before they are ever formatted (`billing/redaction.py`): cardholder name, masked/raw
  card data, tokens and secrets are replaced with `<redacted>`; an agreement id is shown with only
  its last 4 characters.
- **Traceability table:** `billing.BillingTransition` (ADR-014). One append-only row per
  Subscription/PaymentAttempt `state`/`status` change: `environment`, `model_name`, `object_id`,
  `field`, `from_value`, `to_value`, `actor`, `created_at`. Query it directly for "what happened to
  this Subscription/PaymentAttempt and when" — no code anywhere updates or deletes a row here.

## Alert conditions

| Condition | How to detect (today, log/DB query) |
|---|---|
| **Verification failures spike** (forged/invalid-signature webhook deliveries) | Count `event=webhook_rejected reason='invalid_signature'` lines over a window; a sudden spike suggests scanning/attack traffic, not a single misconfigured client. |
| **Uncorrelated events** (a verified event that never matches a `PaymentAttempt`) | Count `event=event_uncorrelated` lines, or `ProviderEvent.objects.filter(processing_status="failed_to_apply", last_error__startswith="uncorrelated")`. Any non-zero count during normal operation needs investigation — Kashier should never report an order Madar didn't create. |
| **Needs-attention events** (an event that exceeded the recovery worker's retry budget) | `ProviderEvent.objects.filter(last_error__startswith="needs_attention")` (written by `process_billing_events`'s own `--max-attempts` path). Each one is a webhook event that could not be applied after repeated attempts and needs a human to read `last_error` and decide. |
| **Unresolved attempts older than threshold** | `PaymentAttempt.objects.filter(status__in=("pending", "unknown"), created_at__lt=<threshold>)`. `reconcile_billing_attempts` already resolves most of these; a growing backlog past its own `--abandon-age-minutes` means the reconciliation worker is not running or Kashier's status-lookup is failing. |
| **Worker not running** | No `event=renewal_run_summary` / `event=reconciliation_run_summary` log line in the expected interval (`--interval` for each `--loop` worker). Absence of the summary line is the signal — there is no separate heartbeat. |

## Manual reconciliation (BILL-RISK-30)

A refund or chargeback issued directly in the Kashier dashboard is never reported back to Madar
through any inbound integration (the webhook only carries *payment-result* events; refund/void
events, if delivered, are stored but never applied — BILL-WU-038, out of scope). After any manual
action in the Kashier dashboard, cross-check the affected `merchant_order_id`/`PaymentAttempt`
against `BillingTransition` and the attempt's current `status` by hand; Madar's own state will not
self-correct.
