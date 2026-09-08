# Operations — Deployment

> **Authority:** Normative (V1 deployment shape).
> **Depends on:** ADR-001, ADR-012.

## Environments

Exactly **three**: development, staging, production. No additional preview environments in V1.

## Deployment shape

- One **Modular Monolith** / one codebase / one deployable application boundary (ADR-001).
- The application runs in **two runtime roles** (ADR-012):
  - **Web / API process** — synchronous requests and the latency-sensitive Fast Session.
  - **Worker process** — asynchronous jobs: notification dispatch, AI operations, and any KB
    publish/index job.
- The worker is **not** a separate service or microservice — it is the **same** application, modules,
  domain model, and persistence, in a different runtime role. This isolates background workload from
  latency-sensitive request handling while preserving the one-deployable decision.

Each environment runs both roles.

## Hosting

Cloud-hosted, managed services wherever practical; avoid self-run infrastructure unless a concrete
requirement later justifies it. **No specific cloud/vendor is selected** at this stage (deferred).
