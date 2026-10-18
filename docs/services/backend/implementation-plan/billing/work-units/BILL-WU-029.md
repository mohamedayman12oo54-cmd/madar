# BILL-WU-029 — Failed-payment outcome recording foundation

**ID:** BILL-WU-029 · **Workstream/Package:** BILL-WS-H / BILL-WP-H1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** BILL-DEC-05. The retry count/schedule and grace duration are **not** encoded here. This unit
records outcomes and leaves the subscription in a "payment failed, access still granted, awaiting policy"
state.
**Priority / Risk:** P0 / High

## Purpose
Separate the decided foundation from the undecided numbers. The foundation persists every attempt
outcome; distinguishes a **confirmed failure** (provider `FAILURE` or a definitive decline code) from an
**ambiguous** outcome (timeout, transport error, `PENDING`, inconclusive lookup); and applies the decided
rule that a single failed renewal does not immediately terminate access.

## Expected outcome
Shared transition functions used by BILL-WU-021 (webhook), BILL-WU-023 (reconciliation) and BILL-WU-025 (renewal):
- `record_confirmed_failure(attempt, provider_code, message)`: the attempt becomes `failed` (terminal),
  with the provider response code and bilingual message stored (Kashier sends `transactionResponseMessage.en/ar`).
  For renewals, the Subscription is marked payment-failed (e.g., `past_due`; name per BILL-WU-008 review),
  `first_failed_at` is set if empty, and failure count is incremented. **Access is unchanged** (BILL-WU-010
  keeps it granted). For a checkout attempt, nothing changes on the subscription; the teacher may retry
  checkout.
- `record_ambiguous(attempt)`: the attempt becomes `unknown`/`pending`; no subscription change; queued for
  reconciliation. **An ambiguous outcome is never recorded as a failure.**
- Everything an Operations person needs to see is captured, without secrets.

## Requirement / invariant references
commercial-model §Failed renewal (no immediate termination; reconcile ambiguous outcomes; limited retries and grace are **expected but unnumbered**); functional §Billing bullet 4; ADR-017 (payment-attempt tracking).

## Relevant ADRs / contracts
ADR-017.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-008 | BLOCKING | Yes | Attempt and Subscription fields |
| BILL-WU-010 | CONTRACT | Yes | The entitlement reading of the failed state |
| BILL-DEC-05 | DECISION | Non-blocking (numbers excluded) | Retry/grace |

## Preconditions
None.

## In-scope changes
Transition functions, tests.

## Explicit exclusions
Retries; grace expiry; restricting access; notifications.

## Implementation surfaces (grounded at bf115df)
`apps/backend/billing/services.py` (or `billing/transitions.py`).

## Data-integrity & security considerations
Terminal-state precedence (a succeeded attempt is never overwritten by a late failure; see BILL-WU-021).

## Failure modes
Misclassifying a timeout as failure (tested); losing the provider code (persisted).

## Acceptance criteria
- **AC-BILL-029-1:** A confirmed failure marks the attempt failed, marks the subscription payment-failed, and the entitlement stays granted.
- **AC-BILL-029-2:** A timeout or `PENDING` is recorded as ambiguous, never failed, and is picked up by reconciliation.
- **AC-BILL-029-3:** No code path in this unit schedules a retry or sets a grace deadline (static review plus test).
- **AC-BILL-029-4:** A failure after success for the same attempt is not applied.

## Verification methods & required evidence
Unit and integration tests.

## Dependencies required before execution
BILL-WU-008, BILL-WU-010.

## Completion definition
AC-1..4 VERIFIED.

## Commit boundaries
`feat(billing): record confirmed and ambiguous payment outcomes`; `test(billing): cover failure versus ambiguity classification`.

## Escalation conditions
Any request to pick retry or grace numbers, or to restrict access on failure.
