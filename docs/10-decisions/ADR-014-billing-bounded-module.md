# ADR-014 — Billing as an Independent Bounded Backend Module

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted. Supersedes nothing. Specializes ADR-001 (Modular Monolith) and ADR-012 (Web/Worker split) by
adding an eighth internal module. A future change requires a new superseding ADR.

## Context
The commercial-design pass (`01-product/commercial-model.md`) confirmed concrete plans, a trial, a
30-day billing cycle, and an access-not-granted principle that must be enforced by code, not only
described in product documentation. No existing module is a natural home for this: `financials` is
explicitly a different, unrelated concept (student-fee tracking) that the documentation already
forbids conflating with the Teacher↔Madar commercial relationship
(`01-product/access-lifecycle.md` §Distinct from student fee tracking). A new module boundary is
required.

## Decision
Introduce **`billing`** as an independent bounded module inside the existing Backend Modular Monolith
(ADR-001) — **not** a microservice, and **not** a merger into `financials`, `accounts`, or
`environments`. It runs in the same deployable, under the same Web/Worker runtime-role split as every
other module (ADR-012), and follows the same internal module-boundary rules as the other seven modules
(private persistence, capability-oriented collaboration, no cross-module direct persistence access —
`services/backend/03-internal-boundaries/module-boundaries.md`).

The `billing` module logically owns (no models or code are created by this decision):
- plans/entitlements,
- subscription state/lifecycle,
- trial state/expiration,
- billing periods,
- invoices/line items where required,
- payment attempts/outcomes,
- saved-payment-method / recurring-agreement references,
- provider-event processing,
- cancellation/renewal scheduling,
- billing traceability records.

Verified against `apps/backend/`'s existing app names (`academics, accounts, ai, config, content,
environments, evaluation, financials, knowledge, notifications, parents, scheduling, studentarea`):
`billing` does not conflict with any existing app name.

## Alternatives considered
- **Extend `financials`** — rejected: the documentation already explicitly forbids merging the two
  money concepts (`01-product/access-lifecycle.md`); doing so would also force an unrelated app to own
  a completely different trust/compliance boundary (payment-provider webhooks vs. record-only fee
  tracking).
- **Extend `accounts` or `environments`** — rejected: billing state is a distinct, sizeable
  responsibility (plans, invoices, payment attempts, provider events) that would overload either
  module's existing, narrower responsibility (actor/auth identity; tenant/environment lifecycle) and
  blur module boundaries the architecture otherwise keeps strict.
- **A separate billing microservice** — rejected for the same reasons ADR-001/ADR-012 already rejected a
  separate worker service: no present operational driver, and it would contradict the one-deployable
  decision without one.

## Consequences
- The Backend now has **eight** internal modules, not seven; `services/backend/04-architecture/architecture.md`,
  `services/backend/00-overview/backend-overview.md`, and the backend structure/context diagrams are
  updated to reflect this as part of this decision pass.
- `billing` depends on other modules only through their explicit internal capabilities (e.g., it would
  consult Identity & Enrollment-owned context to know which Environment a Subscription belongs to), the
  same as every other module — no new exception to BND-1/BND-2 is introduced.
- `billing` is the natural home for the Madar-owned payment-provider interface and Kashier adapter
  (ADR-015) and for the inbound webhook-processing responsibility (ADR-016).
- No models, migrations, views, or application code are created by this ADR — it records the module
  boundary only, ahead of a future Implementation Plan.
