# ADR-018 — Billing-Owned Entitlement Boundary, Integrated With (Not Folded Into) Composite Authorization

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted. Specializes ADR-010 (Composite Authorization) by adding access-state/entitlement as a
distinct, prior input, consistent with TAL-5's existing abstract framing
(`services/backend/01-scope/teacher-access-lifecycle.md`). Does not edit ADR-010. A future change
requires a new superseding ADR.

## Context
TAL-5 already named access-state as "an abstract input alongside composite authorization," deliberately
not a billing architecture. Now that Billing exists as a concrete bounded module (ADR-014) with real
plans/entitlements, this must be made concrete enough to prevent a predictable implementation shortcut:
`accounts/authentication.py`'s `MadarJWTAuthentication.get_user()` is the one place every authenticated
request already passes through, and it already performs a per-request, non-cached check (student
active-enrollment revocation). It would be tempting to bolt entitlement/billing checks onto that same
method simply because it is the available per-request hook. Doing so would conflate two different
kinds of logic with different ownership, different change cadence, and different testing needs.

## Decision
The `billing` module (ADR-014) owns the **commercial decision** of what a given Subscription/Trial
state currently permits (feature access by plan, student-count caps, access-not-granted
consequences). This entitlement-policy decision is **not** dumped into
`MadarJWTAuthentication.get_user()` or any other per-request authentication hook merely because that
hook runs on every request. Instead:

- Billing exposes an explicit **entitlement-policy contract** — a capability other modules/boundaries
  consult, not a side effect embedded inside authentication.
- That contract is consumed at the **correct authorization/application boundary**: after an
  authenticated actor and an authorized tenant/environment context have already been resolved (i.e.,
  after the server-derived tenant context of ADR-008 and the composite-authorization inputs of ADR-010
  are in hand), not before or instead of them.
- Composite authorization (ADR-010: actor + role + authorized environment + relationship/ownership)
  continues unchanged, governing **what** an authorized actor may do within their environment.
  Entitlement governs a **separate, prior** question: **whether** the Teacher currently has access at
  all, and if so, which plan-gated capabilities are currently available.
- Frontend-hiding of gated capabilities is explicitly **insufficient** — entitlement must be enforced at
  the Backend.
- During an access-not-granted state, the entitlement contract must still permit: authentication,
  billing-resolution actions, and data review/export — per the access-not-granted principle
  (`01-product/commercial-model.md`). The entitlement contract is the mechanism that keeps those paths
  open even while gating paid educational capability.

This ADR does **not** fix the exact student-facing restricted-access behavior or the complete
teacher-facing read-only ruleset — those remain open (`01-product/commercial-model.md` §Open items).
It fixes only **where** the entitlement decision is owned and **how** it integrates structurally.

## Alternatives considered
- **Add entitlement checks directly inside `MadarJWTAuthentication.get_user()`** — rejected: conflates
  authentication (who is this actor, is their session valid) with a commercial-policy decision (what
  does their current plan/trial state permit); different ownership (Billing vs. identity/auth), change
  cadence (plan rules change independent of auth mechanics), and testing concerns (billing-state fixtures
  vs. auth fixtures) would otherwise be tangled into one method that already has a narrow, well-tested
  job.
- **Centralize entitlement into the existing composite-authorization model (ADR-010) as a fourth
  factor** — rejected: ADR-010's composite model answers "what may this authorized actor do," a
  structural/relationship question; entitlement answers "does this actor currently have access at all,"
  a commercial-state question that can change on a billing cycle independent of any role/relationship
  change. Keeping them structurally separate (as TAL-5 already proposed in the abstract) avoids
  overloading ADR-010's scope.
- **Enforce entitlement only in the Frontend** — rejected: explicitly insufficient per the
  access-not-granted principle; a client can be bypassed, and paid-capability gating must hold at the
  Backend regardless of Frontend behavior.

## Consequences
- `services/backend/08-cross-cutting/security-authz.md` is updated (this decision pass) to state this
  boundary explicitly, including the caution against folding entitlement into
  `MadarJWTAuthentication.get_user()`.
- A future Implementation Plan must design the entitlement-policy contract's concrete consumption point
  (e.g., a permission-class-level check consulted after `IsEnvironmentMember` resolves context) — not
  designed by this ADR.
- The Worker runtime role (ADR-012) must apply the same entitlement guarantees as the Web role, per the
  existing OP-PARITY principle (`services/backend/09-operations/operations.md`) — a payment-adjacent
  background job gets no weaker trust/entitlement model merely because it runs asynchronously.
