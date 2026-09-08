# Architecture

> **Authority:** Descriptive (the structure). The **decisions** it records are Normative and live in
> `10-decisions/`.
> **Source of truth** for architectural style, module structure, and boundaries.
> **Depends on:** `03-domain/` (the seven sub-domains), the architectural drivers, and the accepted
> ADRs.

## Style: Modular Monolith

Madar V1 is a **Modular Monolith**: one primary deployable application, partitioned internally along
the seven conceptual sub-domains, with centralized tenant/authorization enforcement and Madar-owned
interfaces to external dependencies.

See [ADR-001](../10-decisions/ADR-001-modular-monolith.md) for the full decision.

### Why this style (response to drivers, not preference)

Architecture here is a **response to requirements and constraints**, not a style preference:

- **Team:** three senior engineers (Architect/Backend, Full-Stack, AI; possibly +1 AI). Small,
  senior, low appetite for operational sprawl.
- **Quality priority (ranked):** (1) tenant isolation & data correctness → (2) fast-session
  responsiveness → (3) speed-to-market / operational simplicity → (4) AI cost/latency → (5)
  scalability headroom.
- **No V1 need** for independent deployment or independent scaling of domain areas.

A **layered monolith** was rejected — it does not structurally protect the domain boundaries we
established. **Microservices** were rejected for V1 — they serve only the lowest-ranked driver
(scalability) while actively working *against* the highest (distributed isolation is harder to
guarantee) and against operational simplicity at this team size.

> **Clarification (important):** Madar being a **SaaS** does **not** imply microservices. SaaS
> determines requirements — multi-tenancy, tenant isolation, customer-data boundaries, operational
> scalability — but it does not dictate an architectural style. Microservices may become appropriate
> later if concrete drivers emerge (independent deployment, independently scaling workloads, multiple
> teams, stronger failure isolation). For V1 those drivers are not present strongly enough to justify
> distributed-system complexity. **This is an intentional V1 architecture, not a "couldn't afford
> microservices" compromise.**

The module boundaries are kept clean specifically so that **future extraction** of a component
remains possible if a concrete driver appears — without committing to distribution now.

## The seven modules

Aligned with the conceptual sub-domains from `03-domain/`:

| Module | Responsibility |
|--------|----------------|
| **Identity & Enrollment** | Student (global), Enrollment, Grade, Group, Academic Year |
| **Educational Operations** | Schedule, Session Instance, Attendance, Recitation |
| **Financials** | Grade fee, Payment |
| **Student Evaluation** | State, Rating, Teacher Private Notes |
| **Content** | Video metadata + targeting |
| **Learning & AI** | AI orchestration (Assistant, Quiz, State recommendation) |
| **Notifications** | Notification events + dispatch |

Boundaries are strong and internal: modules collaborate through clear internal interfaces, not by
reaching into each other's data.

## Runtime roles: web + worker

The one deployable runs in **two runtime roles**, sharing the same codebase, modules, domain model,
and persistence:

- **Web / API process** — synchronous requests and the latency-sensitive **Fast Session**.
- **Worker process** — asynchronous jobs: **notification dispatch** and **AI operations** (and any
  KB publish/index job).

The worker is **not** a separate service or microservice — it is the same application in a different
role. This isolates background workload from latency-sensitive request handling while preserving the
one-deployable decision. See [ADR-012](../10-decisions/ADR-012-web-worker-split.md).

## Boundaries & enforcement

- **One unified REST API** for all three clients (Teacher, Student, Content Maintainer), with
  role/tenant/relationship-scoped authorization — [ADR-003](../10-decisions/ADR-003-unified-api-surface.md).
- **Tenant isolation** is enforced in two layers: tenant context established at the request boundary,
  and tenant scope enforced again at the data-access boundary —
  [ADR-004](../10-decisions/ADR-004-two-layer-tenant-isolation.md). The universal isolation key is
  `teacher_environment_id` — [ADR-007](../10-decisions/ADR-007-two-level-data-scoping.md).
- **Authorization** combines authenticated actor + role + authorized environment +
  relationship/ownership; role alone is never sufficient —
  [ADR-010](../10-decisions/ADR-010-composite-authorization.md).
- **External dependencies** (LLM, Push, Video) are consumed through **Madar-owned interfaces** —
  [ADR-009](../10-decisions/ADR-009-provider-interfaces.md). Only **Learning & AI** crosses the LLM
  seam; the model stays outside the boundary — [ADR-002](../10-decisions/ADR-002-ai-internal-module.md).

## Building-block view

See [`building-blocks.md`](building-blocks.md) and
[`diagrams/architecture/building-blocks.mmd`](../diagrams/architecture/building-blocks.mmd).

## Quality-attribute responses (traceability)

| Driver (priority) | Architectural response |
|-------------------|------------------------|
| Tenant isolation (1) | Two-layer enforcement; server-derived context; `teacher_environment_id` universal key |
| Fast-session responsiveness (2) | Per-tap persistence; async notification dispatch off the write path; web/worker split |
| Speed-to-market / simplicity (3) | One deployable, one API, managed services, no premature distribution |
| AI cost/latency (4) | AI bounded module; async + failure-tolerant; selective idempotency on AI submit |
| Scalability headroom (5) | Clean module seams allow later extraction without distributing now |
