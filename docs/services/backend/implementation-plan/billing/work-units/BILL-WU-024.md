# BILL-WU-024 — Billing-period computation (30 elapsed days, server-authoritative)

**ID:** BILL-WU-024 · **Workstream/Package:** BILL-WS-G / BILL-WP-G1
**Status:** READY
**Priority / Risk:** P0 / Medium

## Purpose
One pure, tested implementation of the decided cadence. A billing period is exactly 30 elapsed days,
never a calendar month (commercial-model §Billing period). Renewal-due detection is derived from it.

## Expected outcome
`billing/periods.py`: `next_period(start: aware datetime) -> (start, start + timedelta(days=30))`;
`renewal_due(subscription, now) -> bool`, true when the current paid period ends at or before
`now + lead` (the lead is an operational setting, default 0, documented); `current_period(subscription, now)`.
All arithmetic uses aware UTC instants. `config/months.py` is never imported. The `Africa/Cairo` local
timezone (`settings.py:260-263`) is used only for display.

## Requirement / invariant references
commercial-model §Billing period ("exactly 30 elapsed days"); functional §Billing bullet 3; DAT-5 BillingPeriod.

## Relevant ADRs / contracts
ADR-014.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-008 | BLOCKING | Yes | BillingPeriod model |

## Preconditions
None.

## In-scope changes
Module plus tests (DST transitions in Africa/Cairo, leap days, month-length independence).

## Explicit exclusions
Executing charges (BILL-WU-025); proration.

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/periods.py`; must not import `apps/backend/config/months.py`.

## Data-integrity & security considerations
Contiguous periods: the next period starts exactly at the previous end, with no gaps or overlaps (the
unique (subscription, start) constraint from BILL-WU-008).

## Failure modes
A DST-induced 23 h or 25 h "day" (avoided by elapsed `timedelta` on UTC).

## Acceptance criteria
- **AC-BILL-024-1:** For starts in Feb, Mar and a Cairo DST-change week, `end − start == 30 days` exactly (2,592,000 s).
- **AC-BILL-024-2:** A chain of 13 periods ends 390 days after the first start (no calendar drift).
- **AC-BILL-024-3:** `billing/` contains no import of `config.months`.
- **AC-BILL-024-4:** `renewal_due` is false 1 µs before `end − lead` and true at `end − lead`.

## Verification methods & required evidence
Unit tests.

## Dependencies required before execution
BILL-WU-008.

## Completion definition
AC-1..4 VERIFIED.

## Commit boundaries
`feat(billing): add 30-elapsed-day billing period computation`; `test(billing): cover billing period arithmetic`.

## Escalation conditions
Any request to align periods to calendar months (that contradicts commercial-model; escalate).
