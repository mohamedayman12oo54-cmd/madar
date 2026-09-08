# ADR-004 — Enforce Tenant Isolation at Request/Context and Data-Access Boundaries

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
Multi-teacher isolation (INV-7) is the highest-priority quality attribute. It must be structurally guaranteed — hard to violate by construction — not left to developers remembering to add a tenant filter to each query. Per-teacher physical databases are explicitly **not** required.

## Decision
Enforce isolation in **two layers**: (1) the request/application boundary establishes the authenticated actor and the applicable Teacher-Environment context, carried through the execution path; (2) the data-access boundary enforces the applicable tenant/relationship scope on every teacher-scoped access. Modules cannot bypass this on the normal path. Strong logical isolation, centrally enforced; no per-teacher physical database.

## Alternatives considered
- **Application-enforced scoping only** (single layer) — rejected as insufficient for the #1 driver: one missed filter leaks data.
- **Per-teacher physical database** — rejected: unnecessary operational cost for V1; logical isolation with central enforcement meets the requirement.

## Consequences
- A single missed check does not leak data across tenants.
- The exact mechanism (middleware, DB policies, repository/query patterns, ORM behavior) is deferred to Data/implementation.
- Depends on a single universal scoping key — see ADR-007.
