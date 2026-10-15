# ADR-013 — Permanent One-Teacher-Account-to-One-Teacher-Environment Cardinality

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted. Supersedes nothing (no prior ADR fixed cardinality). Resolves the cardinality item
previously recorded as deferred in `rejected-deferred.md` ("Teacher Environment provisioning trigger &
cardinality"). Does **not** supersede or edit ADR-008; see Consequences for the reconciliation. A
future change to this cardinality rule requires a new superseding ADR.

## Context
Cardinality between a Teacher Account and a Teacher Environment was deliberately left open in the
original lifecycle-correction pass (`03-domain/actor-lifecycles.md`, prior revision;
`services/backend/01-scope/teacher-access-lifecycle.md`, TAL-2). A subsequent commercial-design pass
confirmed, as a settled product/commercial decision, that the Teacher↔Madar commercial relationship
(Subscription) is scoped one-per-Environment, and that the simplest, permanent ownership shape is one
Environment per Teacher Account. Two backend-readiness audits
(`KASHIER_BACKEND_READINESS_AUDIT.md`, `KASHIER_SUPPLEMENTARY_AUDIT.md`) independently found that the
*current* code already leans the other way in three respects: `Environment.owner` is a plain
`ForeignKey` whose own docstring says "a teacher may own several"; `environments/tests.py:26-40`
exercises and asserts two Environments for one teacher; and `ADR-008`'s "authorized environments"
(plural) phrasing was read by the domain docs as evidence for leaving cardinality open. This decision
resolves that conflict explicitly rather than leaving it to accumulate further implicit assumptions.

## Decision
A Teacher Account owns **exactly one** Teacher Environment, **permanently** — this is a domain
invariant (INV-9, `03-domain/invariants.md`), not a V1-only limitation subject to later relaxation by
default. A Teacher who wants a second, separate environment must create a **second Teacher Account**.
There is no supported path, now or planned, for one Teacher Account to own or switch between multiple
Environments.

This decision is **scope-limited to Teacher Account ↔ Teacher Environment cardinality only**. It does
**not** change: Student multi-teacher usage (a Student may still hold Enrollments under multiple
Teacher Environments — unaffected, see INV-7/PD-3); the meaning of `teacher_environment_id` as the
tenant-isolation key; or ADR-008's server-derived-context mechanism, which continues to resolve an
actor against whichever environments it is authorized for, regardless of how many that may be for a
given actor type.

## Alternatives considered
- **Leave cardinality open indefinitely (status quo)** — rejected: blocks a stable scoping axis for the
  Subscription/Billing model (per-Environment vs. per-Teacher-account collapse into the same thing only
  once cardinality is fixed at one); every downstream billing decision would otherwise need to carry a
  hedge.
- **Allow multiple Environments per Teacher Account, with Subscription scoped per-Environment** —
  rejected for V1 and beyond: adds real commercial and product complexity (which environment is "the"
  billed one, proration across environments, confusing account-switcher UX) with no identified business
  driver requiring it; a teacher who genuinely needs a second, independently-run environment is better
  served by a second account.
- **Allow multiple Environments, with Subscription scoped per-Teacher-account (shared across
  Environments)** — rejected: there is no existing tenant-scoping precedent for account-level
  (cross-environment) state (`TenantOwnedModel` is uniformly Environment-scoped today), and it would
  reintroduce the same account/billing-unit ambiguity this ADR exists to remove.

## Consequences
- **INV-9** is added as a binding domain invariant.
- **Reconciles with ADR-008 without editing it.** ADR-008's "authorized environments" (plural) language
  describes the *general* server-derived-context-resolution mechanism — an actor is resolved against
  *whichever* environments it is authorized for — and was never itself a cardinality commitment for any
  specific actor type. ADR-008 remains fully in force and unchanged; this ADR only fixes, for the
  Teacher actor type specifically, that the resolved set has exactly one member.
- **Documentation updated as part of this decision pass** (not a separate future task):
  `03-domain/actor-lifecycles.md`, `services/backend/01-scope/teacher-access-lifecycle.md` (TAL-2),
  `services/backend/06-data/data-model.md` (DAT-4), `10-decisions/rejected-deferred.md`, and the
  Backend implementation-plan's `NODE-EnvProvision`/`R-06` entries now reflect cardinality as
  **resolved**; the provisioning-trigger **mechanism** (automatic vs. explicit action) remains
  separately fenced/open.
- **Implementation follow-up required, not performed by this decision:** enforcing the invariant at the
  Django ORM level (`OneToOneField` is the expected semantic target for `Environment.owner`, replacing
  the current `ForeignKey`) and at the Postgres DB-integrity level; checking any live database for
  pre-existing violating data (not done — no database was queried to produce this decision); and
  updating `environments/tests.py`'s existing multi-environment fixture/test to match the new
  invariant. None of this is implemented by this documentation-only decision.
- Every Subscription/Plan/Trial concept in `01-product/commercial-model.md` is now safely scoped to
  the Teacher Account/Environment pair as a single commercial unit, with no multi-environment
  billing-sharing case to design for.
