# BILL-WU-026 — Kashier 30-day compatibility gate and production renewal activation

**ID:** BILL-WU-026 · **Workstream/Package:** BILL-WS-G / BILL-WP-G2
**Status:** BLOCKED
**Blocked by:** EXTERNAL BILL-EXT-01. Does Kashier's live recurring agreement (`agreement.type=RECURRING`,
`paymentFrequency`, `minimumDaysBetweenPayments`) accept merchant-initiated charges on an exact
30-elapsed-day cadence, and with which parameter values? commercial-model marks this as a
**launch/design gate pending Kashier clarification**. The public guide (reviewed 2026-10-15) shows only a
`MONTHLY` example and a `minimumDaysBetweenPayments` field, and lists no allowed `paymentFrequency`
values, so the guide alone **cannot** prove the guarantee. Also blocked by OPERATIONAL BILL-WU-027 and
VERIFICATION BILL-WU-036.
**Priority / Risk:** P0 for launch / Critical

## Purpose
Turn on production renewals only after Kashier has confirmed **in writing or by a verified sandbox and
live behaviour test** that a 30-elapsed-day merchant-initiated cadence is compatible with the agreement
Madar creates. Fix the agreement parameter values accordingly.

## Expected outcome
1. A recorded BILL-EXT-01 answer (Kashier support/account manager written response plus sandbox evidence):
   the allowed `paymentFrequency` values; whether an `UNSCHEDULED` or `RECURRING` agreement fits;
   `minimumDaysBetweenPayments` semantics; whether charging every 30 elapsed days under a `MONTHLY`
   agreement is permitted, or is constrained to calendar-month dates (a question to **ask**, not an
   assumption); `expiryDate`/`numberOfPayments` implications.
2. If compatible: set agreement configuration values (BILL-WU-018) and enable `BILLING_RENEWALS_LIVE_ENABLED`
   in production, with a staged rollout (one internal merchant test subscription first).
3. If **not** compatible: **stop.** Escalate to product. The 30-elapsed-day rule is normative
   (commercial-model). Neither the plan nor the implementer may switch to calendar months, and choosing an
   alternative (e.g., an unscheduled card-on-file agreement, or a different cadence) is a product/architecture
   decision.

## Requirement / invariant references
commercial-model §Billing period, §Open items (last row), §External verification context; rejected-deferred "Newly deferred" (launch/design gate); backend open-items.

## Relevant ADRs / contracts
ADR-015, ADR-016.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-EXT-01 | EXTERNAL | Yes | The gate |
| BILL-WU-025 | BLOCKING | Yes | Capability to activate |
| BILL-WU-036 | VERIFICATION | Yes | Sandbox evidence of the renewal flow |
| BILL-WU-027 | OPERATIONAL | Yes | Something must run the command in production |
| BILL-EXT-04 | EXTERNAL | Yes | Live merchant account |

## Preconditions
Written question sent to Kashier containing the exact parameters Madar intends to use.

## In-scope changes
Configuration values; feature flag flip; rollout record.

## Explicit exclusions
Any code change to cadence; any calendar-month fallback.

## Implementation surfaces (grounded at bf115df)
`apps/backend/config/settings.py` (agreement parameters, kill switch); `apps/backend/billing/providers/kashier.py` (consumes them).

## Data-integrity & security considerations
Enabling live renewal moves real money. Do it with a monitored first cycle and the BILL-WU-035 alerts in place.

## Failure modes
Kashier rejects a charge for cadence reasons (`failed` with a provider code; caught in the first-cycle watch); an ambiguous answer from Kashier (gate stays closed).

## Acceptance criteria
- **AC-BILL-026-1:** A BILL-EXT-01 answer is recorded with its source (who, when, what) and attached to `risks-and-open-issues.md`.
- **AC-BILL-026-2:** Sandbox evidence shows the saved agreement accepting merchant-initiated charges with the parameters intended for production. Sandbox can't simulate 30 days of elapsed time, so the interval guarantee itself rests on Kashier's written confirmation (AC-1). A sandbox run is not proof of the interval.
- **AC-BILL-026-3:** Production first renewal cycle observed: charge succeeded, period extended by exactly 30 days, no duplicate.

## Verification methods & required evidence
External written confirmation; sandbox logs; production first-cycle ops record.

## Dependencies required before execution
BILL-EXT-01, BILL-WU-025, BILL-WU-036, BILL-WU-027, BILL-EXT-04.

## Completion definition
AC-1..3 met, or the gate formally closed as "incompatible" with a product escalation record (the unit then stays BLOCKED).

## Commit boundaries
`feat(config): enable live billing renewals with verified agreement parameters` (configuration only).

## Escalation conditions
Any incompatible or ambiguous answer; any proposal to "use MONTHLY for now".
