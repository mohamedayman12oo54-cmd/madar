# Cross-Cutting — Observability (Backend)

> **Authority:** **Normative** (the inherited V1 observability floor and exclusion list apply to the
> Backend; the Backend holds them exactly).
> **Specializes:** `../../../08-cross-cutting/observability.md`,
> `../../../10-decisions/ADR-005-async-notification-dispatch.md`,
> `../../../10-decisions/ADR-006-ai-async-failure-tolerant.md`.

The Backend holds the system-level observability floor and exclusion list **exactly**. It introduces
no new observability subsystem and pulls no system-level exclusion back in as a Backend-wide
requirement.

## The observability floor (applied to the Backend)

- **Structured logging + error tracking + basic metrics** where useful.
- The **async / externally-dependent paths** get explicit observability because they fail
  independently:
  - **AI operations** — operation lifecycle/status, latency, success/failure, and failure category
    (client-facing observable lifecycle, `../05-runtime/async-operations.md`).
  - **Notification dispatch** — event processing and delivery-attempt outcomes (internal worker job).
- **KB publish/processing** — observable outcome/failure at the Content-Maintainer-facing boundary
  **when** its outcome affects AI-readiness (`../02-requirements/backend-requirements.md`, BR-3).
- Observability must **avoid logging sensitive student/educational content**.
- Provider-specific AI cost/token telemetry may be added where useful, but is not a core requirement.

## Tiered observability (recap)

The tiering from BR-3 is the operative model: **AI operations** are client-observable with the full
lifecycle; **KB publish/processing** is Content-Maintainer-observable where the outcome matters;
**purely internal worker jobs** (notification dispatch) are internally observable only and do not become
client-facing operations merely because they run asynchronously.

## Security-relevant observability — within the floor, not a new audit layer

The floor may provide operational/security-relevant visibility into failures or rejected attempts at
the authentication, authorization, tenant-context, and isolation boundaries. This does **not** create a
product-wide audit trail. Any such observability must continue to respect the sensitive-data logging
restriction.

## Held exactly — the inherited exclusions (no back-door tightening)

The Backend does **not** reintroduce any of the system-level exclusions as new Backend-wide
infrastructure:

- **No product-wide audit logging** and **no dedicated audit subsystem.**
- **No caching** as a V1 requirement (add only if measured performance requires it).
- **No complex resilience / circuit-breaker infrastructure.**
- **Distributed tracing not mandatory.**
- **No product-wide rate limiting.** Targeted abuse/cost protection for externally-dependent or
  expensive operations remains **permitted only if a concrete need emerges** — "permitted if needed"
  is **not** an architectural commitment that the mechanism exists now, and the Backend does **not**
  pre-commit to an AI-operation rate-limiting/abuse mechanism. If a concrete requirement later
  establishes the need, protection can be introduced then, respecting the selective-idempotency and
  integration boundaries.
- **Universal idempotency not applied** — idempotency is **selective**, required for retryable
  external/stateful commands, especially AI submission (`../../../10-decisions/ADR-011-selective-idempotency.md`).
