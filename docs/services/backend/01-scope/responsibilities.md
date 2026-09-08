# Backend Scope & Responsibilities

> **Authority:** **Normative** for the Backend V1 scope boundary (what the Backend owns / does not own).
> **Specializes:** `../../../01-product/scope.md`, `../../../01-product/product.md`,
> `../../../09-operations/knowledge-base.md`.

The Backend is an **API provider and server-side application boundary**, not a UI renderer. The three
clients (Teacher, Student, Content Maintainer) consume the single unified versioned REST API.

## The two-axis scope model

The Backend scope is **not** a flat feature list. It has two axes: the product/domain capabilities it
realizes, **plus** the mandatory service/runtime responsibilities that constitute the Backend as a
service.

### Axis 1 — Product / Domain capabilities

These are the capabilities the Backend realizes server-side. All are inherited from the established
V1 product/domain scope; the Backend adds no new product capability.

| Capability | Backend responsibility | Upstream |
|------------|------------------------|----------|
| The seven modules | Server-side enforcement and execution of Identity & Enrollment, Educational Operations, Financials, Student Evaluation, Content, Learning & AI, Notifications | `../../../04-architecture/building-blocks.md` |
| Notification behavior & events | The bounded five-event catalog + dispatch | `../../../02-requirements/functional.md` |
| The three AI operations | Study Assistant, AI Quiz, State recommendation (as bounded operations) | `../../../02-requirements/functional.md`, `../../../05-runtime/` |
| Authentication / claiming / context | Server-side **Teacher account authentication** (a distinct actor path) and **student claiming orchestration**; session/context establishment; environment switching | `../../../08-cross-cutting/security-authz.md`, `../../../03-domain/actor-lifecycles.md`, `teacher-access-lifecycle.md` (TAL-1) |
| Teacher & Environment lifecycle | Represent Teacher account/actor, **Environment establishment + initial empty state**, and the **Teacher→Student introduction** connection into the existing claiming model | `../../../03-domain/actor-lifecycles.md`, `teacher-access-lifecycle.md` (TAL-1/2/4) |
| Access state (trial/subscription) | Represent an **abstract access-state input** to the access-decision boundary — *whether* a Teacher currently has access; **not** a billing architecture | `../../../01-product/access-lifecycle.md`, `teacher-access-lifecycle.md` (TAL-5) |
| **KB authoring / publishing** | The Content-Maintainer-facing KB application surface + publish orchestration (see the KB seam below) | `../../../09-operations/knowledge-base.md` |
| Provider-facing capabilities | Backend-side integration of the three Madar-owned provider interfaces | `../../../07-contracts/external-interfaces.md` |

### Axis 2 — Service / Runtime responsibilities

These are not independent product capabilities; they are mandatory parts of the Backend service
boundary. Where applicable:

- API request handling and contract enforcement
- authentication and server-side session/context establishment
- composite authorization
- tenant/environment and relationship/ownership enforcement
- domain-rule and invariant enforcement
- persistence and transaction coordination
- asynchronous operation/job lifecycle management
- Backend-side idempotency/retry boundaries
- uniform error semantics
- observability of relevant synchronous and asynchronous paths
- integration with the Madar-owned external provider interfaces
- Web/Worker runtime responsibilities within the single deployable

## The KB / Content-Maintainer seam (three-way cut)

The Knowledge Base seam is divided precisely so that Backend application responsibility, open storage
technology, and AI-internal implementation are never conflated.

**The Backend owns:**
1. **The Content-Maintainer KB authoring API** — the server-side surface to create, edit, manage,
   and publish KB content; its validation, authorization, and scope enforcement; the application-level
   KB lifecycle/state; and the publish operation's server-side lifecycle semantics.
2. **Application-level KB persistence behavior** — whatever persistence behavior is required to
   support the Content-Maintainer API and the authoritative KB lifecycle. **The concrete KB storage
   technology is Open** — an Architecture/Data decision, not pre-assigned to either the Backend or the
   AI Module.
3. **Publish → processing orchestration** — if publishing requires asynchronous processing/indexing,
   the Backend/Worker owns the runtime orchestration boundary (triggering the work, integrating it
   with the operation/job lifecycle, exposing the relevant state/failure at the Backend boundary),
   consistent with the Web/Worker model.

**The AI Module owns** (behind that boundary): indexing implementation, retrieval/RAG design,
ingestion internals, embeddings/chunking, AI-specific processing pipelines, and provider-specific AI
implementation.

> **Guardrail.** This documentation does **not** conclude that "the KB store belongs to the AI
> Module." The application-level KB authoring/persistence responsibility is part of the Backend
> boundary; the concrete storage technology remains Open; the AI-specific indexing/retrieval
> implementation belongs to the later AI Module Documentation. The system's statement that the KB
> lives in "its own knowledge store, not ordinary transactional data" is a statement about
> *separateness*, not ownership, and is consistent with this cut.

## Out of Backend scope (by default)

- **Client / UI concerns** — the Frontend (the three client surfaces).
- **AI internals** — prompting, model selection, RAG, ingestion, embeddings, algorithms,
  provider-specific AI implementation → the AI Module Documentation.
- **External provider implementations & vendor selection** — deferred (Implementation / Operations).
- **Retention / deletion / privacy / legal policy** — an Operations follow-up, not yet binding
  (`../../../06-data/lifecycle-retention.md`, `../../../08-cross-cutting/security-authz.md`).
- **Homework** — **fenced** from the V1 Definition-of-Done. The Backend builds nothing for it unless
  the feasibility gate passes (`../../../01-product/scope.md`).
- **Commercial / billing mechanics** — pricing, plans, billing provider/gateway, invoicing, trial
  duration, renewal, cancellation, payment processing → deferred to a commercial-design pass; the
  Backend represents only an **abstract access-state input**, not a billing architecture
  (`teacher-access-lifecycle.md`, TAL-5).
- **Lifecycle mechanisms left unresolved upstream** — Teacher authentication mechanism; Environment
  provisioning trigger & per-Teacher cardinality; the secure Teacher→Student invitation mechanism; the
  exact access-not-granted behavior (suspension/grace/read-only) → all **fenced**
  (`teacher-access-lifecycle.md`; `../../../10-decisions/rejected-deferred.md`).

## Scope closure

The Backend's V1 scope is the union of the Axis-1 capabilities and the Axis-2 responsibilities above.
The System Documentation's lifecycle-correction pass added **upstream lifecycle responsibilities**
(Teacher account/authentication, Environment establishment + initial state, the Teacher→Student
introduction connection, and an abstract access-state input) — these are **responsibility-boundary
additions**, not new product/domain capabilities, and are consolidated in
`teacher-access-lifecycle.md` with every unresolved mechanism fenced. No other server-side
product/domain capability is introduced. Scope remains **closed** at this level, subject to the
standing rule that genuinely system-impacting discoveries are **escalated** (see `../README.md`), not
silently absorbed into the Backend.
