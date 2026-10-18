# BILL-WU-016 — Repeat-trial / trial-abuse controls

**ID:** BILL-WU-016 · **Workstream/Package:** BILL-WS-D / BILL-WP-D1
**Status:** BLOCKED
**Blocked by:** DECISION BILL-DEC-04. commercial-model §Free trial: "Repeat-trial / anti-abuse policy:
explicitly **Open** — not decided, not defaulted." INV-9 makes "create a new account" the sanctioned way
to get a new environment, which makes repeat-trial abuse structurally easy.
**Priority / Risk:** P1 / Medium

## Purpose
Once BILL-DEC-04 decides it, implement whatever eligibility rule applies to trials for new accounts (which
might be "no control in V1").

## Expected outcome
Shape only: an eligibility check inside `start_trial` (BILL-WU-014) or at signup start, per the decided
rule. **Nothing is implemented before the decision.** In particular, phone/email uniqueness
(`accounts/models.py:50-51`) is not to be treated as an abuse control by assumption.

## Requirement / invariant references
commercial-model §Free trial (open item), §Open items.

## Relevant ADRs / contracts
ADR-013 (new account = new environment).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-DEC-04 | DECISION | Yes | Policy |
| BILL-WU-014 | BLOCKING | Yes | Hook point |

## Preconditions
BILL-DEC-04 recorded.

## In-scope changes
Per decision.

## Explicit exclusions
Any fingerprinting or device tracking without a decision and a privacy review.

## Implementation surfaces (grounded at bf115df)
`apps/backend/billing/services.py` (`start_trial`); `apps/backend/accounts/serializers.py` (signup start).

## Data-integrity & security considerations
Any identity-linking signal is personal data (privacy posture deferred to Operations, `security-authz.md`).

## Failure modes
A legitimate teacher wrongly refused a trial.

## Acceptance criteria
- **AC-BILL-016-1:** The behaviour matches the recorded BILL-DEC-04 rule, with a test per rule branch. If the decision is "no control in V1", this AC is satisfied by a recorded decision plus a test that a second account still gets a trial.

## Verification methods & required evidence
Tests; decision record.

## Dependencies required before execution
BILL-DEC-04.

## Completion definition
AC-1 VERIFIED, or a recorded "no control" decision. Required before BILL-WU-037 as a DECISION dependency (the decision must exist, even if it is "none").

## Commit boundaries
`feat(billing): apply trial eligibility rule`.

## Escalation conditions
Any request to implement a control before the decision.
