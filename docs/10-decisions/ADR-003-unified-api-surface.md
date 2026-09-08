# ADR-003 — Use One Unified API Surface

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
Three web clients (Teacher, Student, Content Maintainer) consume the backend. A prior project (SentinelX) suffered from uncoordinated, divergent contract consumers. The question is how many API surfaces to expose.

## Decision
**One unified, versioned REST API** for all three clients, with role/tenant/relationship-scoped authorization. Clients may have different allowed operations and response shapes but remain consumers of the same boundary.

## Alternatives considered
- **Separate Teacher/Student API products** — rejected: duplicates semantics and invites divergence, the exact SentinelX failure mode. Not justified at V1 scale.

## Consequences
- Smaller contract surface to govern; one coherent set of semantics.
- Role-specific authorization instead of surface duplication.
- Fixed target for the Contracts stage; no consumer invents its own truth.
