# BILL-WU-035 — Billing observability, audit trail, log redaction

**ID:** BILL-WU-035 · **Workstream/Package:** BILL-WS-J / BILL-WP-J1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** NODE-Vendors (no APM or error-tracking vendor; logging is console-only, `config/settings.py:559+`).
Alerts are defined as log events plus a query or runbook until a vendor exists.
**Priority / Risk:** P1 / Medium

## Purpose
Make money-state transitions traceable and safe to log. The existing logging has no field redaction
(audit §10.5), so billing must add its own.

## Expected outcome
A `billing` logger with structured key=value lines for: event received, verified, rejected (no body),
duplicate, applied, uncorrelated, mismatched; attempt created, charged, outcome; reconciliation results;
renewal run summaries. A redaction helper strips or masks `cardHolderName`, `maskedCard`, token,
agreement id (last 4 only) and every key or secret, and is applied before logging or before storing raw
webhook bodies (BILL-WU-008). An immutable transition-history record (who/what/when/from→to) for
Subscription and PaymentAttempt changes provides billing traceability (ADR-014 "billing traceability
records"). A runbook lists alert conditions: verification failures spike; uncorrelated events;
needs-attention events; unresolved attempts older than threshold; worker not running.

## Requirement / invariant references
ADR-014 (traceability records); configuration-secrets (no secrets in logs); observability (no sensitive content); BR-3.

## Relevant ADRs / contracts
ADR-017.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-017 | CONTRACT | Yes | Secrets catalogue to redact |
| BILL-WU-020 | CONTRACT | Yes | Webhook logging points |

## Preconditions
None.

## In-scope changes
Logger config entry, redaction helper, transition-history model (billing-private), runbook.

## Explicit exclusions
Selecting an APM vendor.

## Implementation surfaces (grounded at bf115df)
`apps/backend/config/settings.py` LOGGING (`:559+`); `apps/backend/billing/*`.

## Data-integrity & security considerations
The history record is append-only (no update/delete paths in code).

## Failure modes
A secret leaks via exception repr (tests feed secrets through error paths and assert absence).

## Acceptance criteria
- **AC-BILL-035-1:** Tests capture logs during webhook, checkout and renewal flows and assert no key, secret, full token, cardholder name or masked PAN appears.
- **AC-BILL-035-2:** Every Subscription/PaymentAttempt state change writes one history row.
- **AC-BILL-035-3:** The runbook exists and lists each alert condition with how to detect it.

## Verification methods & required evidence
Log-capture tests; review.

## Dependencies required before execution
BILL-WU-017, BILL-WU-020.

## Completion definition
AC-1..3 VERIFIED.

## Commit boundaries
`feat(billing): add billing audit trail and log redaction`; `test(billing): assert no secrets or card data in logs`.

## Escalation conditions
Need for a vendor before launch (Operations decision).
