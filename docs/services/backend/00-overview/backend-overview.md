# Backend Overview

> **Authority:** Descriptive · **Specializes** the System Documentation for the Backend service.
> **Upstream:** `../../../00-overview/system-overview.md`, `../../../04-architecture/architecture.md`.

## What the Backend is

The Backend is the **server-side application boundary within Madar's V1 Modular Monolith**. It is not
the Modular Monolith itself — the Modular Monolith is the *system's* architectural style and boundary
(`../../../10-decisions/ADR-001-modular-monolith.md`); the Backend is the *service/documentation
boundary* being specialized here, distinct from the Frontend (the three clients) and from the later
AI Module.

The Backend is the server-side unit through which every deterministic guarantee Madar makes is
ultimately **enforced**: tenant isolation, data correctness, domain invariants, and the teacher's
authority over advisory AI. It exposes the single unified REST API, runs in the **web** and
**worker** runtime roles (`../../../10-decisions/ADR-012-web-worker-split.md`), and contains the eight
internal modules, including **Learning & AI** as an internal bounded module
(`../../../10-decisions/ADR-002-ai-internal-module.md`) and **Billing** as an internal bounded module
added by the commercial-design pass (`../../../10-decisions/ADR-014-billing-bounded-module.md`).

## Why it matters

The clients render; the external providers are consumed outbound; the AI internals live behind a
seam. But the guarantees that make Madar trustworthy — that Teacher B never reaches Teacher A's
records, that a monthly record never silently loses its academic context, that an AI failure never
corrupts deterministic data — are all realized **in the Backend**. That is the reason this service
documentation exists: to make those guarantees implementable and to keep them non-bypassable.

## The Backend's neighbor set

The Backend boundary faces five classes of neighbor. This is the complete set for V1.

| Class | Members | Nature |
|-------|---------|--------|
| **Inbound clients** | Teacher, Student, Content Maintainer | Consume the one unified REST API (`../../../07-contracts/api-contract.md`) |
| **Outbound provider integrations** | LLM, Push, Video, **Payment (Kashier)** | Consumed through Madar-owned interfaces (`../../../07-contracts/external-interfaces.md`); Payment's outbound side follows the same shape, see Negative space below for its inbound exception |
| **Infrastructure / data dependencies** | Persistence datastore, KB store | Depended-on infrastructure at the edge of the Backend boundary; **not** peer external systems; concrete technology **Open** |
| **Internal seam** | AI Module (Learning & AI) | Behind the Backend-owned integration contract (`../07-contracts/backend-ai-integration-contract.md`) |
| **Conditional / deferred** | OTP / Identity-Verification mechanism | Dependency of the Backend-orchestrated claiming flow; **whether it takes the form of an external provider is undecided** |

**Negative space (inherited, narrowly amended):** Teacher, Student, and Content Maintainer act *on*
Madar; LLM/Push/Video remain outbound only. The **one** exception is the Payment provider's
signature-verified payment-result webhook — the system's sole approved inbound external integration
(`../../../10-decisions/ADR-016-inbound-webhook-exception.md`). No other inbound external integration
exists in V1.

See `../diagrams/context/backend-context.mmd`.

## Scope in one paragraph

The Backend's V1 scope is modeled on **two axes** (full detail in `../01-scope/responsibilities.md`):
its **Product/Domain capabilities** (the eight modules' behavior, the five notification events, the
three AI operations, authentication/claiming/context, KB authoring/publishing, and the
provider-facing capabilities) **plus** its **Service/Runtime responsibilities** (API serving,
authorization/isolation enforcement, persistence/invariant enforcement, async execution/orchestration,
uniform error semantics, observability, external-interface integration, and Web/Worker runtime
behavior). The Backend is an **API provider, not a UI renderer**.

## How the Teacher and Environment come to exist (lifecycle framing)

The capability documents in this tree describe what the Backend does for an **authenticated Teacher
operating an established Environment**. The System Documentation's lifecycle-correction pass made the
**upstream** chain explicit — *product entry → Teacher account → Teacher authentication → Environment
establishment (empty) → initial use → Teacher introduces students → existing Student lifecycle* — plus
a parallel **Free Trial → Subscription** access lifecycle
(`../../../03-domain/actor-lifecycles.md`, `../../../01-product/access-lifecycle.md`). The Backend-level
responsibilities this creates — Teacher account/authentication, Environment establishment and initial
empty state, the Teacher→Student introduction connection, and an abstract access-state input — are
documented in `../01-scope/teacher-access-lifecycle.md`, with every unresolved mechanism explicitly
**fenced**. The Student identity/claiming model is **unchanged**.

## Design-first stance

This documentation specifies intended design; it does not assume an implementation exists. The
**technology stack is fully Open** — language, framework, database, ORM, hosting, queue — and no
stack choice is inferred from the absence of a decision. Technology selection is
requirements-and-fitness first, and is routed to the appropriate later stage.

## Where to read next

1. `../01-scope/responsibilities.md` — what the Backend owns and where its boundaries are
2. `../03-internal-boundaries/module-boundaries.md` — the internal rules (read before architecture)
3. `../04-architecture/architecture.md` — the internal structural model
