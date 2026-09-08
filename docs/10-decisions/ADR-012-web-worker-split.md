# ADR-012 — Web/Worker Runtime Split Within One Deployable

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
Runtime made notification dispatch and AI operations asynchronous (ADR-005, ADR-006), while the Fast Session is latency-sensitive (#2 driver). Background work must not compete with latency-sensitive request handling — but ADR-001 commits to one deployable.

## Decision
Run the Modular Monolith in **two runtime roles** sharing the same codebase, modules, domain model, and persistence: a **web/API process** for synchronous requests and the Fast Session, and a **worker process** for asynchronous jobs (notification dispatch, AI operations, any KB publish/index job). The worker is **not** a separate service or independently owned microservice.

## Alternatives considered
- **Everything in the web process** — rejected: background/AI/notification work would compete with latency-sensitive Fast Session handling.
- **A separate worker service/microservice** — rejected: contradicts ADR-001's one-deployable decision without a present driver.

## Consequences
- Background load is isolated from latency-sensitive requests.
- The one-deployable Modular Monolith decision is preserved (same codebase/domain/persistence).
- Three environments (dev/staging/prod) each run both roles.
