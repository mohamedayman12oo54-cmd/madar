# Architectural Decisions

> **Authority:** **Normative.** Accepted ADRs are binding on implementation and on all downstream
> service documentation.
> **Source of truth** for architectural decisions and their rationale.

Each ADR records **Context · Decision · Alternatives · Consequences · Status**, preserving *why* the
decision was made and what was rejected — not only the final state. A decision, once accepted, is
stable; a future change produces a **new** ADR that supersedes the old one rather than editing it.

Not every choice is an ADR. These eighteen cross the bar of being architecturally significant —
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
| [ADR-013](ADR-013-permanent-environment-cardinality.md) | Permanent one-Teacher-Account-to-one-Teacher-Environment cardinality | Accepted |
| [ADR-014](ADR-014-billing-bounded-module.md) | Billing as an independent bounded Backend module | Accepted |
| [ADR-015](ADR-015-payment-provider-interface.md) | Madar-owned payment-provider interface (Kashier), extending ADR-009 | Accepted |
| [ADR-016](ADR-016-inbound-webhook-exception.md) | Narrow inbound-webhook exception for Kashier payment-result callbacks | Accepted |
| [ADR-017](ADR-017-payment-event-idempotency.md) | Payment-event integrity distinct from client-request idempotency | Accepted |
| [ADR-018](ADR-018-billing-entitlement-boundary.md) | Billing-owned entitlement boundary, integrated with composite authorization | Accepted |

See also [`rejected-deferred.md`](rejected-deferred.md) — the negative register that preserves
architectural intent by recording what was explicitly rejected and what was deferred.
