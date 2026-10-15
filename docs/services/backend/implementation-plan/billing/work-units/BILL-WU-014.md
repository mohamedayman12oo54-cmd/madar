# BILL-WU-014 — Start the 16-day trial inside the atomic teacher-signup transaction

**ID:** BILL-WU-014 · **Workstream/Package:** BILL-WS-D / BILL-WP-D1
**Status:** READY
**Priority / Risk:** P0 / High (touches the account-creation transaction)

## Purpose
Implement commercial-model §Free trial. The trial starts at "the instant the Teacher Account is
activated **and** its Environment is successfully established", which in code is a single atomic event.
The trial-start instant is the Backend's own timestamp, never client-supplied.

## Expected outcome
Inside `TeacherSignupEnvironmentView.post` (`apps/backend/accounts/views.py:157-200`), **within** the
existing `with transaction.atomic():` block (`:174-191`), right after
`EnvironmentMembership.objects.create(...)` (`:191`), the view calls a Billing-owned capability, for
example `billing.services.start_trial(environment=env, activated_at=now)`, where `now = timezone.now()`
is captured once on the server. This creates the Environment's Subscription in trial state with
`trial_start = now` and `trial_end = now + timedelta(days=16)`, with **no** payment method and **no**
auto-conversion. Any failure in `start_trial` raises inside the atomic block, so the user, Environment,
membership and `consume_pending` all roll back (the existing all-or-nothing comment, `:168-172`, is
preserved and extended). The response shape (`:200`) is unchanged. Optionally (non-breaking) it gains
nothing; trial status is fetched from the billing API (BILL-WU-031).

## Requirement / invariant references
commercial-model §Free trial (16 days, at activation + environment establishment, no card, Plan 3 features, cap 250, no auto-convert); functional §Billing bullet 2; INV-9.

## Relevant ADRs / contracts
ADR-014 (Billing owns trial state); BND-1 (accounts calls a Billing capability; it doesn't write Billing tables).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-008 | BLOCKING | Yes | Subscription persistence |
| BILL-WU-009 | DATA | Yes | Trial = Plan 3 capability set |
| BILL-WU-006 | DATA | Non-blocking | One Subscription per Environment = per account once INV-9 is DB-enforced |

## Preconditions
Re-read `accounts/views.py:157-200` and `accounts/tests.py:60-100` (existing signup tests).

## In-scope changes
`billing/services.py: start_trial`; the call inside the atomic block; tests.

## Explicit exclusions
Legacy accounts (BILL-WU-015); repeat-trial checks (BILL-WU-016; **no** eligibility check is added here
because that policy is open); trial-expiry notifications (BILL-WU-033); any client-provided timestamp;
calendar arithmetic.

## Implementation surfaces (grounded at bf115df)
`apps/backend/accounts/views.py:174-191`; new `apps/backend/billing/services.py`; `apps/backend/accounts/tests.py`.

## Data-integrity & security considerations
The atomic block already catches `IntegrityError` (`:192-198`) and returns 409 "phone/email in use". An
`IntegrityError` from the Subscription insert would be mis-reported as that conflict. `start_trial` must
not raise `IntegrityError` for a new Environment (unique per Environment, and the Environment was just
created). Add a test that injects a billing failure and asserts full rollback.

## Failure modes
Billing failure aborts signup (intended: all-or-nothing); a timezone-naive `now` (USE_TZ guarantees aware);
a replayed `pending_id` creates no second trial (existing `consume_pending` guard, `:175`).

## Acceptance criteria
- **AC-BILL-014-1:** After successful signup, exactly one Subscription exists for the new Environment, in trial state, with `trial_end − trial_start == 16 days` and `trial_start` within the request's server time window.
- **AC-BILL-014-2:** The request body cannot influence trial start or duration (a test sends extra fields; they are ignored).
- **AC-BILL-014-3:** If `start_trial` raises, no User, Environment, membership or Subscription row exists afterwards, and the pending flow is still consumable (rollback test).
- **AC-BILL-014-4:** Replaying the same `pending_id` yields 400 and no second Subscription (extends `accounts/tests.py:96-100`).
- **AC-BILL-014-5:** Entitlement for the new environment is granted with Plan 3 capabilities and cap 250.
- **AC-BILL-014-6:** No payment-method reference exists on the trial Subscription.

## Verification methods & required evidence
Integration tests via the signup endpoints; rollback injection test.

## Dependencies required before execution
BILL-WU-008, BILL-WU-009.

## Completion definition
AC-1..6 VERIFIED.

## Commit boundaries
`feat(billing): add trial start capability`; `feat(accounts): start billing trial inside teacher signup transaction`; `test(accounts): cover trial creation atomicity`.

## Escalation conditions
Any proposal to start the trial outside this transaction, or at first login, or from client time.
