# BILL-WU-011 — Entitlement enforcement integration (permission layer after tenant resolution; plan-gated AI on Web and Worker)

**ID:** BILL-WU-011 · **Workstream/Package:** BILL-WS-C / BILL-WP-C2
**Status:** READY WITH A TRACKED OPEN ITEM
**Open items:** BILL-DEC-07 (whether the general Study Assistant `assistant` kind is plan-gated; which AI
kinds map to `ai.performance_analysis`). BILL-DEC-02 (what happens to **non**-plan-gated capability when
access is not granted) is excluded here and BLOCKED in BILL-WU-013.
**Priority / Risk:** P0 / High (authorization boundary)

## Purpose
Consume the BILL-WU-010 contract at the correct boundary: **after** `IsEnvironmentMember` has resolved
`request.environment` from the `X-Madar-Environment` header and membership (ADR-008), and **outside**
`MadarJWTAuthentication.get_user()` (ADR-018). Enforce the plan-gated capabilities that are already
decided (the AI features per plan) on both the Web and Worker paths (OP-PARITY).

## Expected outcome
1. A DRF permission factory in `billing`, for example `RequiresCapability("ai.quiz_from_video")`. It
   **must be listed after** `IsEnvironmentMember` in `permission_classes`. DRF evaluates permissions in
   list order, and `IsEnvironmentMember.has_permission` sets `request.environment`
   (`environments/tenancy.py:114-123`). The factory reads `request.environment`, calls
   `billing.entitlements.decide(...)`, and raises a stable `APIException` subclass (e.g., code
   `entitlement_required` / `capability_not_in_plan`, status chosen per NODE-WireAPI hand-off) when the
   capability is absent. If `request.environment` is missing, it **fails loudly** (like
   `TenantScopedQuerySetMixin`, `tenancy.py:136-139`). It never reads a tenant from body or query.
2. **How the Environment and membership context are resolved before the check.** Teacher endpoints use
   `IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]` (e.g., `ai/views.py:14`), then
   `RequiresCapability(...)`. Student endpoints (`studentarea/views.py:55-56`, `STUDENT` permissions)
   resolve the teacher's Environment the same way (header plus active Enrollment,
   `tenancy.py:88-96`). The capability is evaluated against **that Environment's** Subscription (the
   teacher's plan), never the student's.
3. Applied to plan-gated submission endpoints only:
   - Teacher state-recommendation submit (`ai/views.py:70-104`) → `ai.performance_analysis` (mapping per BILL-DEC-07).
   - Student quiz request (`studentarea/views.py:282-318`) → `ai.quiz_from_video`.
   - `assistant` submit (`ai/views.py:17-68` POST; `studentarea/views.py:384-389`): **not gated until
     BILL-DEC-07 decides.** Leave a marked TODO referencing BILL-DEC-07; do not guess.
   - Reads of existing AI results (detail/list GETs) are **not** gated (data review per the
     access-not-granted principle).
4. **Worker parity.** `process_ai_operations.py` claims and executes operations submitted while
   entitled. Record the entitlement decision basis on submission (submit-time check). On the worker,
   either re-check before calling the provider, or document the submit-time rule. Implement the
   **re-check**: an operation whose Environment lost the capability between submit and processing ends
   `failed` with a stable error, which is consistent with "no partial result" (ADR-006). This is a small
   addition at `process_ai_operations.py:79-80`, after the claim and before the provider call. The worker
   reconstructs context from `op.environment_id` (server-created state), satisfying OP-PARITY.
5. **Always-permitted categories are never decorated:** `/api/v1/auth/*`, `/api/v1/billing/*`
   resolution/checkout/status endpoints, and read endpoints used for data review.

## Requirement / invariant references
ADR-018; TAL-5; AL-2; security-authz §Explicit caution; OP-PARITY; EX-1/EX-3; commercial-model §Plans, §Access-not-granted.

## Relevant ADRs / contracts
ADR-008, ADR-010 (composite authz unchanged and still evaluated), ADR-018, ADR-006, ADR-012.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-010 | CONTRACT | Yes | Consumes the decision |
| BILL-WU-014 | DATA | Non-blocking for code; blocking for meaningful production behaviour | New teachers need trial state, otherwise every gated call is denied |
| BILL-WU-015 | DATA | Blocking for launch | Legacy teachers have no Subscription, so they would be denied at launch |
| BILL-DEC-07 | DECISION | Non-blocking | Assistant gating left explicit |

## Preconditions
Re-read `environments/tenancy.py:100-128` and each target view's `permission_classes`.

## In-scope changes
`billing/permissions.py`; edits to the listed views' `permission_classes`; AI worker re-check; tests.

## Explicit exclusions
**Any change to `accounts/authentication.py`.** Gating of non-AI educational capabilities (BILL-WU-013).
Student-cap (BILL-WU-012). Frontend hiding.

## Implementation surfaces (grounded at bf115df)
`apps/backend/billing/permissions.py` (new); `apps/backend/ai/views.py:14,22,75`;
`apps/backend/studentarea/views.py:282-318,384-389`;
`apps/backend/ai/management/commands/process_ai_operations.py:76-95`; `apps/backend/config/exceptions.py`
(envelope; no change needed).

## Data-integrity & security considerations
Ordering bug risk: if `RequiresCapability` is placed before `IsEnvironmentMember`, it would have no
environment. Fail closed and loudly; a test asserts ordering on every decorated view. A cross-tenant
attempt (teacher B with A's header) must still yield `environment_forbidden`, **not** an entitlement
error. This proves entitlement doesn't leak another tenant's subscription state.

## Failure modes
Legacy teacher locked out at deploy (handled by BILL-WU-015 gate before launch); worker re-check denies an
op mid-flight (ends `failed` cleanly); decision computed with a naive clock (tests).

## Acceptance criteria
- **AC-BILL-011-1:** A Plan 1 environment can submit a student quiz request; a state-recommendation submit is refused with a stable entitlement code.
- **AC-BILL-011-2:** A trial (unexpired) environment can use every Plan 3 gated capability.
- **AC-BILL-011-3:** An expired-trial environment with no subscription is refused gated AI submissions but can still GET existing AI results, log in, and reach billing endpoints.
- **AC-BILL-011-4:** Teacher B with Teacher A's environment header gets `environment_forbidden` (the tenant check precedes the entitlement check) on every decorated endpoint.
- **AC-BILL-011-5:** Every decorated view lists `RequiresCapability` after `IsEnvironmentMember` (automated test iterating URL patterns).
- **AC-BILL-011-6:** An AIOperation submitted while entitled, whose environment loses the capability before processing, ends `failed` with no Quiz row created.
- **AC-BILL-011-7:** `accounts/authentication.py` is byte-identical to baseline (diff check) and has no `billing` import.
- **AC-BILL-011-8:** The `assistant` kind's gating status matches the recorded BILL-DEC-07 outcome (until decided: ungated, with a TODO referencing BILL-DEC-07).

## Verification methods & required evidence
Integration tests via `TenantTestCase` (`environments/tenancy_testing.py`); worker test with `--max-iterations 1`; static checks; review.

## Dependencies required before execution
BILL-WU-010.

## Completion definition
AC-1..8 VERIFIED.

## Commit boundaries
`feat(billing): add capability permission consulted after tenant resolution`; `feat(ai): gate plan-gated AI submissions on billing capability`; `test(billing): cover entitlement enforcement ordering and parity`.

## Escalation conditions
Any proposal to check entitlement inside authentication; gating a student-facing feature not mapped by commercial-model; restricting reads.
