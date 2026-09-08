# Cross-Cutting — Observability & Explicit Exclusions

> **Authority:** Normative (the V1 observability floor and the explicit exclusion list).
> **Depends on:** `04-architecture/`, ADR-005, ADR-006.

## Observability floor (V1)

- **Structured logging + error tracking + basic metrics.**
- **Distributed tracing is not mandatory** for the V1 modular monolith.
- The **async / externally dependent paths** get explicit observability because they fail
  independently:
  - **AI operations** — operation lifecycle/status, latency, success/failure, and failure category.
  - **Notification dispatch** — event processing and delivery-attempt outcomes.
- Observability must **avoid logging sensitive student/educational content**.
- Provider-specific AI cost/token telemetry may be added where useful, but is not a core requirement.

## Explicitly N/A for V1 (recorded, not omitted)

These are deliberately **not** V1 cross-cutting concerns; recording them prevents over-engineering and
prevents silent reintroduction:

- **Caching** — not a V1 requirement; add only if measured performance requires it.
- **Complex resilience / circuit-breaker infrastructure** — not required.
- **Distributed tracing** — not mandatory.
- **Generalized / product-wide audit logging** — not required; ordinary domain history remains where
  the product explicitly needs it.
- **Product-wide rate limiting** — not required; targeted abuse/cost protection may be introduced for
  externally dependent or expensive operations if needed.
- **Universal idempotency** — not applied; idempotency is **selective**, required for retryable
  external/stateful commands, especially AI submission (ADR-011).
