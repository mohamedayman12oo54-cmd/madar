# ADR-008 — Server-Derived, Non-Client-Controllable Tenant Context

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
Isolation must hold at the contract, not only the data layer. If a client could supply an arbitrary tenant id, isolation would leak through the API — the SentinelX-class failure mode.

## Decision
`teacher_environment_id` is **never** accepted as an arbitrary client-controlled tenant selector. On each request the server authenticates the actor, resolves them against their **authorized** environments, and establishes the active environment context **server-side**. An actor may **explicitly switch** only among environments they are authorized to access. Data-access enforcement (ADR-004/007) then applies the established context.

## Alternatives considered
- **Client-supplied tenant id** — rejected: allows a client to target another tenant; defeats INV-7 at the API.
- **Implicit single-tenant assumption** — rejected: students legitimately belong to multiple environments and must switch (see the multi-teacher scope rule).

## Consequences
- The API cannot be used to reach another tenant's data.
- A student's context is exactly one active authorized environment at a time; no cross-environment merge.
- Tenant isolation is a contract rule, not a client responsibility.
