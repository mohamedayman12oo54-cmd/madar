# Architectural Decisions

> **Authority:** **Normative.** Accepted ADRs are binding on implementation and on all downstream
> service documentation.
> **Source of truth** for architectural decisions and their rationale.

Each ADR records **Context · Decision · Alternatives · Consequences · Status**, preserving *why* the
decision was made and what was rejected — not only the final state. A decision, once accepted, is
stable; a future change produces a **new** ADR that supersedes the old one rather than editing it.

Not every choice is an ADR. These twelve cross the bar of being architecturally significant —
someone will later need to understand why they were made. Minor implementation choices are not
recorded here.

## Register

| ADR | Decision | Status |
|-----|----------|--------|
| [ADR-001](ADR-001-modular-monolith.md) | Modular Monolith for V1 | Accepted |
| [ADR-002](ADR-002-ai-internal-module.md) | AI as an internal bounded module | Accepted |
| [ADR-003](ADR-003-unified-api-surface.md) | One unified API surface | Accepted |
| [ADR-004](ADR-004-two-layer-tenant-isolation.md) | Two-layer tenant isolation | Accepted |
| [ADR-005](ADR-005-async-notification-dispatch.md) | Asynchronous notification dispatch | Accepted |
| [ADR-006](ADR-006-ai-async-failure-tolerant.md) | AI is async and failure-tolerant | Accepted |
| [ADR-007](ADR-007-two-level-data-scoping.md) | Two-level data scoping | Accepted |
| [ADR-008](ADR-008-server-derived-tenant-context.md) | Server-derived tenant context | Accepted |
| [ADR-009](ADR-009-provider-interfaces.md) | Madar-owned external provider interfaces | Accepted |
| [ADR-010](ADR-010-composite-authorization.md) | Composite authorization | Accepted |
| [ADR-011](ADR-011-selective-idempotency.md) | Selective idempotency | Accepted |
| [ADR-012](ADR-012-web-worker-split.md) | Web/worker runtime split within one deployable | Accepted |

See also [`rejected-deferred.md`](rejected-deferred.md) — the negative register that preserves
architectural intent by recording what was explicitly rejected and what was deferred.
