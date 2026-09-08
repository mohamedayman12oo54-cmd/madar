# Backend Decision Register (Light)

> **Authority:** **Normative** (records the Backend-level decisions and their classification).
> **Depends on:** the inherited ADRs in `../../../10-decisions/` (referenced, **not** duplicated).

This is the **Light Backend Decision Register** — the consolidated Backend-level decision record. It
preserves traceability and classifies each entry by its actual nature and authority. It does **not**
promote every entry into an ADR.

## Classification model

| Class | Meaning |
|-------|---------|
| **Inherited System Decision** | Established upstream; referenced from the System ADRs, not restated. |
| **Backend Service-Level Decision** | A Backend-specific specialization or boundary decision recorded with enough context to explain it. |
| **Rule / Principle / Model** | An established Backend rule, principle, or model — documented as such, not promoted into an ADR. |
| **Open / Deferred** | A decision or detail whose status is explicitly open, with an owner. |

At documentation time, **only** entries that genuinely require ADR-level treatment receive the fuller
Context → Decision → Alternatives → Consequences structure. The rest stay lightweight with traceability
to their originating stage or inherited decision.

## The register

| # | Entry | Class | Originating stage | Home / reference |
|---|-------|-------|-------------------|------------------|
| BD-1 | Backend = server-side application boundary **within** the Modular Monolith (not "is" the monolith) | Backend Service-Level Decision | Discovery | `../00-overview/backend-overview.md` |
| BD-2 | Design-first: specify intended design; infer no technology from absence of a decision; stack fully Open | Backend Service-Level Decision | Discovery | `../README.md`, `../00-overview/backend-overview.md` |
| BD-3 | Two-axis scope model: Product/Domain capabilities **+** Service/Runtime responsibilities | Backend Service-Level Decision | Product & Scope | `../01-scope/responsibilities.md` |
| BD-4 | KB seam three-way cut: Backend owns authoring API + app-level persistence + publish orchestration; store tech Open; AI owns indexing/retrieval | Backend Service-Level Decision | Product & Scope | `../01-scope/responsibilities.md` |
| BD-5 | Invariant enforcement is hard and non-bypassable on every applicable write path — **Backend specialization of an already-established guarantee** (not a new/strengthened system decision) | Rule / Principle / Model | Requirements | `../02-requirements/backend-requirements.md` (BR-1) |
| BD-6 | Fast-Session minimal per-tap synchronous transaction; no numeric latency SLA | Rule / Principle / Model | Requirements | `../02-requirements/backend-requirements.md` (BR-2) |
| BD-7 | Tiered async observability (client Operations vs. Content-Maintainer-facing KB vs. internal Jobs) | Rule / Principle / Model | Requirements | `../02-requirements/backend-requirements.md` (BR-3) |
| BD-8 | Private per-module persistence; capability-oriented collaboration; no cross-module data reads | Rule / Principle / Model | Domain | `../03-internal-boundaries/module-boundaries.md` (BND-1) |
| BD-9 | Cross-cutting context/isolation enforcement vs. per-module ownership authorization split | Rule / Principle / Model | Domain | `../03-internal-boundaries/module-boundaries.md` (BND-2) |
| BD-10 | Emitting module owns atomic domain-write + durable event hand-off within its own boundary; Notifications consumes/dispatches | Backend Service-Level Decision | Domain / Architecture | `../04-architecture/architecture.md`, `../03-internal-boundaries/module-boundaries.md` (BND-3) |
| BD-11 | Internal structural model: capabilities over private persistence + cross-cutting controls; no prescribed layering | Rule / Principle / Model | Architecture | `../04-architecture/architecture.md` |
| BD-12 | Trusted execution context reconstructed on the Worker path; never client-derived/unscoped-privileged | Rule / Principle / Model | Architecture | `../04-architecture/execution-model.md` (EX-1) |
| BD-13 | Common async principles, but Operation vs. Job remain structurally distinct | Backend Service-Level Decision | Architecture | `../04-architecture/execution-model.md` (EX-2) |
| BD-14 | AI Module gets no structural exception (module rules apply; distinction is responsibility + integration) | Rule / Principle / Model | Architecture | `../04-architecture/architecture.md` |
| BD-15 | Canonical async-operation runtime spine (Quiz, State-recommendation); Assistant interaction model Open/Deferred | Backend Service-Level Decision | Runtime | `../05-runtime/async-operations.md` |
| BD-16 | `teacher_environment_id` = uniform structural isolation attribute ≠ shared ownership | Rule / Principle / Model | Data | `../06-data/data-model.md` (DAT-1) |
| BD-17 | Backend↔AI = internal capability contract; specify-to-seam, defer internals; + uniform internal-capability-contract style | Backend Service-Level Decision | Contracts | `../07-contracts/backend-ai-integration-contract.md`, `../07-contracts/internal-contracts.md` |
| BD-18 | Semantic internal→external failure mapping asserted; wire-level taxonomy deferred | Rule / Principle / Model | Contracts | `../07-contracts/external-api-alignment.md` (AL-1) |
| BD-19 | Secrets/provider-config cross-cutting principle (what); operational how deferred | Rule / Principle / Model | Cross-Cutting | `../08-cross-cutting/configuration-secrets.md` |
| BD-20 | Guarantee-parity across environments + runtime roles (not infra parity) | Rule / Principle / Model | Operations | `../09-operations/operations.md` (OP-PARITY) |
| BD-21 | Teacher account/actor + Teacher authentication is a Backend responsibility (distinct from student claiming); mechanism fenced | Backend Service-Level Decision | Alignment pass (upstream `03-domain/actor-lifecycles.md`, `08-cross-cutting/security-authz.md`) | `../01-scope/teacher-access-lifecycle.md` (TAL-1) |
| BD-22 | Environment establishment + initial empty state recognized as a Backend lifecycle point; provisioning trigger & per-Teacher cardinality fenced | Backend Service-Level Decision | Alignment pass (upstream `03-domain/actor-lifecycles.md`) | `../01-scope/teacher-access-lifecycle.md` (TAL-2) |
| BD-23 | Teacher→Student introduction represented only as the connection into the existing claiming model; invitation mechanism fenced; Student model unchanged | Backend Service-Level Decision | Alignment pass (upstream `03-domain/actor-lifecycles.md`) | `../01-scope/teacher-access-lifecycle.md` (TAL-4) |
| BD-24 | Access state (Free Trial/Subscription) treated as an abstract access-decision input, separate from and prior to composite authz; not a billing architecture; commercial mechanics fenced | Backend Service-Level Decision | Alignment pass (upstream `01-product/access-lifecycle.md`) | `../01-scope/teacher-access-lifecycle.md` (TAL-5) |

## Inherited System Decisions (referenced, not restated)

The Backend entries above specialize or build on these accepted ADRs, which remain canonical upstream:
`ADR-001` (modular monolith), `ADR-002` (AI internal module), `ADR-003` (unified API), `ADR-004`
(two-layer isolation), `ADR-005` (async notification dispatch), `ADR-006` (AI async/failure-tolerant),
`ADR-007` (two-level data scoping), `ADR-008` (server-derived tenant context), `ADR-009` (provider
interfaces), `ADR-010` (composite authorization), `ADR-011` (selective idempotency), `ADR-012`
(web/worker split). See `../../../10-decisions/`.

## The escalation rule

A Backend entry is valid only while it stays within established system boundaries and does **not**
redefine: system boundaries, established invariants, external/client-facing contracts, the
tenant/isolation model, external integration contracts, or inherited ADRs. Any Backend decision that
would change one of those must be **explicitly escalated to the System Documentation level** rather than
resolved silently inside the Backend documentation.

> **No entry in this register is system-impacting.** Each either specializes within an inherited ADR or
> fills a service-level gap the system explicitly left open.
