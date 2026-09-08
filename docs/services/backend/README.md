# Madar — Backend Service Documentation

> **Authority:** Normative (navigation + Backend source-of-truth map).
> **Scope:** The **Backend service** of Madar V1 — the server-side application boundary within
> Madar's V1 Modular Monolith. This documentation **specializes** the System Documentation for the
> Backend; it does not redefine it.
> **Upstream authority:** `../../` (the System Documentation `docs/` tree). Every system-level truth
> is **referenced** here, never duplicated or restated as an independent copy.
> **Status:** Design-first / pre-implementation. This documentation specifies the intended V1
> server-side design, boundaries, contracts, responsibilities, runtime behavior, and implementation
> guidance. It does **not** document an existing implementation, and it does **not** infer a
> technology, architecture, or pattern from the absence of an explicit decision.

The Backend is the **server-side application boundary within Madar's V1 Modular Monolith** — the one
place through which the system exposes its single unified REST API and enforces authentication,
composite authorization, server-derived tenant isolation, domain rules and invariants, persistence,
and asynchronous processing, and through which it consumes its three outbound external dependencies
(LLM, Push, Video). It is **not** an independently deployed microservice; it is the server-side unit
of the Modular Monolith, running in the web and worker runtime roles, and it contains the seven
internal modules — including **Learning & AI** as an internal bounded module.

---

## Relationship to the System Documentation

```
System Documentation (../../)         ← establishes system-wide truth (AUTHORITATIVE)
        │
        └── Backend Service Documentation (this tree)
                 → specializes the Backend within that system truth
                 (AI Module Documentation and Frontend Service Documentation
                  will specialize further, from System + the Backend/AI contract here)
```

Lower-level documentation may elaborate higher-level documentation, but may not redefine it. If a
Backend-level discovery ever requires a system-level decision to change, it is **escalated** to the
System Documentation and resolved there — never silently resolved inside this tree. See the
**escalation rule** below.

---

## Authority model

Each Backend artifact carries one of three authority levels, identical in meaning to the system's:

- **Normative** — implementation MUST comply. Applies here **only to Backend service-level truth**
  (Backend scope, internal boundaries, Backend behavior rules, the Backend-owned seam contracts).
- **Descriptive** — explains the Backend as designed.
- **Informative** — helps the reader (navigation, open-item control).

**A Backend artifact is Normative only for Backend service-level truth that does not touch
system-level normative truth.** System-level normative truth (invariants, the tenant model, the
external/client-facing API contract, accepted ADRs) stays canonical **upstream** and is referenced,
not re-asserted, here.

---

## Backend source-of-truth map

| Knowledge | Canonical home |
|-----------|----------------|
| Backend orientation & neighbor set | `00-overview/backend-overview.md` |
| Backend scope (two-axis model) & KB seam cut | `01-scope/responsibilities.md` (Normative for Backend scope) |
| Teacher access & lifecycle boundary (account/auth, environment establishment, Teacher→Student connection, access state) | `01-scope/teacher-access-lifecycle.md` (Normative for the boundary; mechanisms fenced) |
| Backend behavior requirements | `02-requirements/backend-requirements.md` (Normative) |
| Internal module boundaries & collaboration rules | `03-internal-boundaries/module-boundaries.md` (Normative) |
| Backend internal structural model | `04-architecture/architecture.md` |
| Web/Worker execution model & async execution rules | `04-architecture/execution-model.md` (Normative) |
| Canonical async-operation runtime spine | `05-runtime/async-operations.md` |
| Fast-Session Backend runtime | `05-runtime/fast-session.md` |
| Backend logical data-behavior model | `06-data/data-model.md` |
| Internal module-capability contract style | `07-contracts/internal-contracts.md` (Normative) |
| **Backend ↔ AI integration contract (the seam)** | `07-contracts/backend-ai-integration-contract.md` (Normative; collaboratively owned) |
| External REST-contract alignment | `07-contracts/external-api-alignment.md` |
| Backend security/authz split & observability | `08-cross-cutting/` |
| Secrets/config principle | `08-cross-cutting/configuration-secrets.md` |
| Backend operations (confirm-and-route) | `09-operations/operations.md` |
| Backend Decision Register | `10-decisions/decision-register.md` (Normative) |
| Coherence & open items | `11-validation/` |

## Upstream source-of-truth map (referenced, not owned here)

| System-level knowledge | Canonical home (upstream) |
|------------------------|---------------------------|
| System boundary, actors, external dependencies | `../../00-overview/system-overview.md` |
| Domain concepts & terminology | `../../00-overview/glossary.md` |
| Domain model, ownership, invariants, lifecycles | `../../03-domain/` |
| Teacher account & Environment lifecycle | `../../03-domain/actor-lifecycles.md` |
| Free Trial → Subscription (access lifecycle) | `../../01-product/access-lifecycle.md` |
| Architectural style, modules, boundaries | `../../04-architecture/architecture.md` |
| Internal API contract (Normative) | `../../07-contracts/api-contract.md` |
| External provider interfaces (Normative) | `../../07-contracts/external-interfaces.md` |
| Architectural decisions (Normative) | `../../10-decisions/ADR-*.md` |
| Rejected & deferred register | `../../10-decisions/rejected-deferred.md` |

---

## The AI seam locator (consolidated by reference, not duplicated)

The Backend ↔ AI relationship is **defined once** in
`07-contracts/backend-ai-integration-contract.md`. Every other place that touches AI **references**
that seam rather than restating it. Where each piece lives:

| AI-integration piece | Where it is defined |
|----------------------|---------------------|
| The seam contract (capabilities, direction, context, results/failure, persistence coordination, idempotency boundary) | `07-contracts/backend-ai-integration-contract.md` |
| AI Module structural placement (no structural exception) | `04-architecture/architecture.md` |
| Canonical async-operation spine (Quiz, State-recommendation) | `05-runtime/async-operations.md` |
| AI product-state persistence facts (ownership **Open**) | `06-data/data-model.md` |
| LLM as external dependency behind a Madar-owned interface | `../../07-contracts/external-interfaces.md` (upstream) |
| AI internals (prompting, model, RAG, embeddings, algorithms) | **Out of scope here** — the later AI Module Documentation |

---

## The escalation rule (standing governance)

A Backend entry is valid only while it stays within established system boundaries. Anything that
would **redefine** any of the following must be **escalated to the System Documentation level**, not
resolved locally:

- system boundaries,
- established invariants,
- external / client-facing contracts,
- the tenant / isolation model,
- external integration contracts,
- inherited architectural decisions (accepted ADRs).

---

## Reading order

```
README  →  00-overview  →  01-scope  →  03-internal-boundaries  →  04-architecture
        →  05-runtime  →  06-data  →  07-contracts  →  10-decisions/decision-register
```

Start at `00-overview/backend-overview.md`. Read `03-internal-boundaries` before `04-architecture`
(the architecture assumes the internal-boundary rules).

---

## A note on what this documentation deliberately leaves open

This is design-first documentation. A number of items are **explicitly Open/Deferred**, each with an
owner and a reason it is non-blocking; they are recorded — not resolved — here. The consolidated list
is `11-validation/open-items.md`. Documentation must **not** resolve any of them implicitly (no stack
choice, no concrete mechanism, no schema/endpoint catalog, no ownership inference where ownership is
open).
