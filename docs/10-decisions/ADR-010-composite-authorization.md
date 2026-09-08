# ADR-010 — Composite Authorization (Role + Tenant + Relationship/Ownership)

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
Authorization must resolve three things at once: the actor's role, the tenant boundary (isolation), and the multi-teacher relationship/ownership scope. Role-based access alone cannot express 'this teacher, in their own environment, for records they own'.

## Decision
Every authorization decision combines **authenticated actor + role + authorized Teacher-Environment context + relationship/ownership scope**. Role alone is never sufficient; tenant and relationship checks are mandatory. Teacher → own environment and its records; Student → one active authorized environment, only their own Enrollment's records; Content Maintainer → central content/KB surface only, **no** teacher educational records. No finer-grained permission matrix is required for V1.

## Alternatives considered
- **Role-only (RBAC)** — rejected: cannot express tenant + ownership scoping; would allow cross-tenant/cross-owner access.
- **A fine-grained permission matrix** — rejected as unnecessary for V1's small, well-defined role set.

## Consequences
- One canonical authz model that ADR-004 and ADR-008 build on.
- Content Maintainer is explicitly walled off from educational records.
- Simple enough for a three-person team to reason about and enforce centrally.
