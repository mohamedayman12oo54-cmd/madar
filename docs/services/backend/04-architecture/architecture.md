# Backend Architecture — Internal Structural Model

> **Authority:** Descriptive (the structure); the **boundary rules it asserts are Normative** for the
> Backend.
> **Specializes:** `../../../04-architecture/architecture.md`,
> `../../../04-architecture/building-blocks.md`, `../../../10-decisions/ADR-001-modular-monolith.md`,
> `../../../10-decisions/ADR-002-ai-internal-module.md`.
> **Diagram:** `../diagrams/structure/backend-modules.mmd`.
> **Design-first note:** this asserts structural **responsibilities and boundaries** only. It does
> **not** prescribe an implementation-layer pattern (e.g., "Application → Domain → Infrastructure"),
> nor repositories, handlers, framework middleware, or any concrete pattern. Those remain
> implementation choices; the technology stack is Open.

## The structural model (responsibilities, not a layering pattern)

The Backend asserts three structural facts and one invariant.

### 1. Strong horizontal module boundaries

- Each of the eight modules (including Billing, added by ADR-014) owns its domain responsibilities and
  its **private persistence**.
- Each module exposes explicit **internal capabilities** through its module boundary for cross-module
  collaboration.
- No module directly accesses or mutates another module's private persistence, even though everything
  remains inside one Modular Monolith and one deployable (`../03-internal-boundaries/module-boundaries.md`).

Conceptually, a module is **internal capabilities over its owned domain responsibilities and private
persistence**, wrapped by cross-cutting execution controls — and no further structural prescription is
made.

### 2. Cross-cutting execution controls

Authentication context, server-derived tenant/environment context, structural isolation enforcement,
common authorization infrastructure, invariant enforcement, and relevant execution/observability
controls apply across **all applicable execution paths**. These are cross-cutting concerns — **not** an
additional generic business module, and **not** a substitute for module-owned domain authorization
rules (`../03-internal-boundaries/module-boundaries.md`, BND-2).

### 3. Multiple execution paths over the same module structure

The Web/API path and the Worker path both execute against the same module boundaries, domain
responsibilities, and persistence ownership. The same non-bypassable isolation and invariant
guarantees hold regardless of whether execution originates from an HTTP request or a worker job. The
execution model is detailed in `execution-model.md`.

### The key architectural invariant

> Cross-module collaboration occurs through explicit module capabilities; cross-module direct
> persistence access is prohibited; cross-cutting guarantees apply across every applicable execution
> path.

## The eight modules within the Backend

Inherited from `../../../04-architecture/building-blocks.md` (responsibilities and dependency directions
are authoritative there for the original seven; **Billing** is added by
`../../../10-decisions/ADR-014-billing-bounded-module.md` following the commercial-design pass).
Within the Backend they follow the boundary rules above uniformly:

| Module | Owns (domain responsibility) | Notes at the Backend |
|--------|------------------------------|----------------------|
| Identity & Enrollment | Student (global), Enrollment, Grade, Group, Academic Year | Foundation capability provider for others |
| Educational Operations | Schedule, Session Instance, Attendance, Recitation | Emits Absent / Not-Studied event hand-offs (BND-3) |
| Financials | Grade fee, Payment (student→teacher fee tracking) | Resolves fee via Identity & Enrollment capability; **unrelated to Billing** |
| Student Evaluation | State, Rating, Teacher Private Notes | Consults Learning & AI for advisory State recommendation |
| Content | Video metadata + targeting | Uses the Video interface; blob external |
| Learning & AI | AI orchestration (see below) | Sole crosser of the LLM seam |
| Notifications | Notification events + dispatch | Async consumer of event hand-offs; uses Push interface |
| **Billing** | Plan/Subscription/BillingPeriod/Invoice/PaymentAttempt/provider-event/entitlement (DAT-5) | Sole crosser of the payment-provider seam; owns the system's one approved inbound integration (ADR-016); see BND-4 |

## The transactional event hand-off pattern

To satisfy both the atomicity requirement
(`../../../10-decisions/ADR-005-async-notification-dispatch.md`) and per-module persistence privacy
(BND-1), the Backend asserts this shape — **without** naming Outbox, queue, broker, polling, CDC, or
any concrete mechanism (all Open):

> The emitting module owns the transactional event hand-off within its own persistence/transactional
> boundary. The domain record and the durable event hand-off commit atomically as part of the emitting
> module's transaction. The Notifications module does not write into the emitting module's persistence
> and does not own the emitter's event record.

```
Emitting module
  • domain state
  • durable event hand-off
  • atomic commit of both within its own transactional boundary
        │
        ▼   (asynchronous consumption)
Notifications
  • consumes the hand-off
  • performs notification dispatch
  • handles applicable retries/failures
  • integrates with the Push provider interface
```

This preserves ADR-005 atomicity (no committed domain state without its required durable notification
hand-off) **and** BND-1 persistence privacy (no module writes into another's private persistence).

## AI Module structural placement — no structural exception

The AI Module (Learning & AI) receives **no structural exception** from the module model. It is one of
the eight modules and follows the same rules (Billing, per BND-4, likewise receives no exception):

- It owns its explicitly assigned AI-related domain responsibilities and the private persistence
  assigned to those responsibilities.
- It exposes explicit internal capabilities through its module boundary; other modules cannot directly
  access or mutate its private persistence.
- It participates in the same cross-module capability model and is subject to the same applicable
  cross-cutting context, isolation, authorization, invariant, and execution guarantees.
- It operates across the same Web/Worker runtime structure where applicable.

Its distinction is about **responsibility and integration**, not boundary rules:

1. It is the module responsible for the AI-specific domain capabilities assigned to it.
2. It is the **sole** module crossing the LLM integration seam.
3. The **Backend ↔ AI integration contract** is the explicit boundary between the Backend's
   application-level integration responsibility and the AI Module's internal implementation
   (`../07-contracts/backend-ai-integration-contract.md`).
4. The AI Engineer owns the internal AI design behind that contract.

> **Guardrail.** Do **not** infer module ownership of specific domain entities merely because they are
> AI-related. Ownership must remain consistent with the established domain/building-block decomposition
> and is specified further only where the module documentation requires it. AI internals (prompting,
> model selection, RAG, ingestion, embeddings, algorithms, AI pipelines, provider specifics) are
> **outside the scope of this Backend documentation** and belong to the AI Module Documentation.

> **The architectural point:** AI is a first-class internal module, not a privileged or exceptional
> architectural boundary. Its specialization does not exempt it from the Backend's module-boundary,
> persistence-privacy, cross-cutting-enforcement, or execution-path rules.
