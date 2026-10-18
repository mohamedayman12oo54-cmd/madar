# BILL-WU-033 — Billing notifications to the teacher

**ID:** BILL-WU-033 · **Workstream/Package:** BILL-WS-I / BILL-WP-I2
**Status:** BLOCKED
**Blocked by:** DECISION BILL-DEC-06 (System-level). The existing notification capability can't carry
teacher billing messages without a decision:
- `apps/backend/notifications/models.py:1-17,24-39`: the `Notification` catalog is the **five** documented
  student events (`absent`, `not_studied`, `new_video`, `rating_published`, `broadcast`). "The recipient is
  the STUDENT's account row." The channels are "in-app + push only". Adding billing types extends a
  catalog that `02-requirements/functional.md` §Notifications bounds to five events (System-level truth).
- The push provider is a no-op (`notifications/providers.py:30-36`, `NullPushProvider`), so push delivery doesn't exist yet.
- Email and SMS exist **only** for OTP (`accounts/delivery.py:1-12`). `07-contracts/api-contract.md`
  §negative space ("No SMS/WhatsApp/email") and `../implementation-plan.md` §3 negative space exclude
  them as notification channels.
- `process_notifications.py` lacks an atomic claim (audit R3), so it isn't safe to extend as-is.

commercial-model §Failed renewal expects "a clear notification to the teacher plus recovery instructions",
so this is a **launch prerequisite**.
**Priority / Risk:** P0 for launch / High

## Purpose
Once BILL-DEC-06 chooses channel and catalog, notify teachers of trial ending/ended, renewal success,
renewal failure with recovery instructions, and cancellation effective.

## Expected outcome
Shape only, per decision. One option is an in-app billing banner derived from the billing API with no
new channel. That option may satisfy the decision without touching the notification catalog, but the
choice is BILL-DEC-06's, not this plan's.

## Requirement / invariant references
commercial-model §Failed renewal; functional §Notifications (bounded catalog); ADR-005; BND-3 (emitting module owns event semantics).

## Relevant ADRs / contracts
ADR-005, ADR-009.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-DEC-06 | DECISION | Yes | Channel and catalog |
| BILL-WU-014, BILL-WU-029, BILL-WU-028 | DATA | Yes | Event sources |

## Preconditions
Decision recorded (likely System docs update by its owner).

## In-scope changes
Per decision.

## Explicit exclusions
Adding email/SMS or new notification types without the decision.

## Implementation surfaces (grounded at bf115df)
`apps/backend/notifications/models.py`, `notifications/services.py`, `notifications/management/commands/process_notifications.py` (if extended, add an atomic claim first); or `billing` API only.

## Data-integrity & security considerations
Notification content must not include card or token data.

## Failure modes
Duplicate sends (fix the claim first if the notification worker is reused).

## Acceptance criteria
- **AC-BILL-033-1:** (finalized after BILL-DEC-06) Each decided billing event reaches the teacher via the decided channel exactly once per occurrence.

## Verification methods & required evidence
Integration tests per decided channel.

## Dependencies required before execution
BILL-DEC-06.

## Completion definition
AC-1 VERIFIED.

## Commit boundaries
`feat(notifications): deliver billing notifications to teachers` (or `feat(billing): ...` per decision).

## Escalation conditions
Starting before BILL-DEC-06.
