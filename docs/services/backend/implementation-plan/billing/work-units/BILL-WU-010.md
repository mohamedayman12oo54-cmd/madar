# BILL-WU-010 — Entitlement-policy contract (Billing-owned capability)

**ID:** BILL-WU-010 · **Workstream/Package:** BILL-WS-C / BILL-WP-C1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** BILL-DEC-02. The contract reports *that* access is not granted and *why*. What
consumers do about general (non-plan-gated) capability in that state is BLOCKED in BILL-WU-013. BILL-DEC-05:
the grace state after a failed renewal has no numeric duration, so the contract exposes a
"payment-failed, access still granted" state without inventing an expiry.
**Priority / Risk:** P0 / High

## Purpose
Provide the single, explicit entitlement-policy contract ADR-018 requires. It is a Billing-owned
capability answering "does this Environment's Teacher currently have access, and to which plan-gated
capabilities and student cap?" It is consumed by other boundaries and never embedded in authentication.

## Expected outcome
A provider-neutral, side-effect-free function or service, for example
`billing.entitlements.decide(environment, *, now) -> EntitlementDecision`. It returns: `access_granted`
(bool); `basis` (trial / paid-active / paid-past-due-within-unbounded-grace / cancelled-but-paid-through /
none); `capabilities` (set of keys from BILL-WU-009); `student_cap` (int or None); `period_end` or
`trial_end`; `reason_code` (stable machine code for API mapping). `now` is injected so tests are
deterministic; production passes `timezone.now()`.

Derivation rules (only decided rules; nothing invented):
- Trial: granted iff `trial_start ≤ now < trial_start + 16 days` (elapsed time, server instants).
  Capabilities = Plan 3; cap = 250.
- Paid: granted iff a succeeded payment covers a BillingPeriod with `start ≤ now < end`. Capabilities and
  cap come from that period's plan.
- Cancel-at-period-end: still granted until the paid period ends (commercial-model §Cancellation).
- A single failed renewal does **not** terminate access (commercial-model §Failed renewal). Until
  BILL-DEC-05 sets retry/grace numbers, the contract keeps `access_granted=True` with basis
  `payment_failed_pending_policy` and **flags** the condition. It doesn't invent an expiry. This interim
  behaviour is itself a tracked open item: it is "no termination", which is decided, but "how long" is not.
- Otherwise: not granted, reason `trial_expired` / `no_subscription` / `period_ended`.
- **Always-permitted categories** (independent of decision): authentication, billing resolution,
  data review/export (ADR-018; commercial-model §Access-not-granted). The contract exposes a helper
  saying these categories are always allowed, so enforcement can't accidentally gate them.

## Requirement / invariant references
ADR-018; TAL-5; commercial-model §Free trial, §Billing period, §Cancellation, §Failed renewal, §Access-not-granted; functional §Billing bullets 2-5; BND-1/BND-4.

## Relevant ADRs / contracts
ADR-018, ADR-010 (unchanged), ADR-008 (context resolved first), OP-PARITY.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-008 | BLOCKING | Yes | Reads Subscription/BillingPeriod |
| BILL-WU-009 | DATA | Yes | Capability keys, caps |
| BILL-DEC-02, BILL-DEC-05 | DECISION | Non-blocking (surfaced as state, not behaviour) | See open items |

## Preconditions
None beyond the dependencies.

## In-scope changes
`billing/entitlements.py` (decision type plus function), internal capability documentation, unit tests
with a frozen clock across all bases and boundary instants (exactly at 16 days, exactly at period end).

## Explicit exclusions
Any enforcement point (BILL-WU-011/012/013); any HTTP or JWT code; caching of the decision (not
introduced; if needed later, it must be invalidated on every billing state transition); any read of
`financials`.

## Implementation surfaces (grounded at bf115df)
New `apps/backend/billing/entitlements.py`. **Not** `apps/backend/accounts/authentication.py:17-29`.

## Data-integrity & security considerations
Pure read; deterministic on `now`. Boundary semantics are half-open intervals `[start, end)`. Uses aware
UTC instants. `TIME_ZONE=Africa/Cairo` (`settings.py:260-263`) must not affect elapsed-day arithmetic.

## Failure modes
Off-by-one at boundaries (tested); DST shifting a "day" (avoided by `timedelta(days=16)` on aware UTC
instants); missing Subscription row for a legacy teacher (returns `no_subscription`; BILL-WU-015 decides
what legacy accounts get).

## Acceptance criteria
- **AC-BILL-010-1:** Trial granted at `start` and at `start + 16d − 1µs`; not granted at `start + 16d`.
- **AC-BILL-010-2:** Paid period granted on `[start, start+30d)`, not at `start+30d` without a covering succeeded payment.
- **AC-BILL-010-3:** With `cancel_at_period_end`, access is granted until period end and not after.
- **AC-BILL-010-4:** After one failed renewal attempt the decision is still `access_granted=True` with a payment-failed basis; no numeric grace expiry is encoded.
- **AC-BILL-010-5:** Capabilities and cap follow BILL-WU-009 for each plan; trial = Plan 3 capabilities, cap 250.
- **AC-BILL-010-6:** Always-permitted categories (auth, billing, export) are reported allowed regardless of decision.
- **AC-BILL-010-7:** Static check: `accounts/authentication.py` doesn't import `billing`.

## Verification methods & required evidence
Unit tests with an injected clock; static import check; review.

## Dependencies required before execution
BILL-WU-008, BILL-WU-009.

## Completion definition
AC-1..7 VERIFIED; open items recorded in module docstring.

## Commit boundaries
`feat(billing): add entitlement-policy decision contract`; `test(billing): cover entitlement decision boundaries`.

## Escalation conditions
Any pressure to choose a grace duration, restricted-access behaviour, or to evaluate entitlement inside authentication.
