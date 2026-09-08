# Backend ↔ AI Integration Contract (the Seam)

> **Authority:** **Normative** for the Backend-owned integration seam with the Learning & AI module.
> **Primary ownership:** **Collaborative — Backend/Architecture + AI Engineer.** The Backend owns the
> integration boundary; the AI Engineer owns the internal implementation behind it; the contract is
> designed collaboratively, and **neither side may unilaterally redefine it**.
> **Specializes:** `../../../10-decisions/ADR-002-ai-internal-module.md`,
> `../../../10-decisions/ADR-009-provider-interfaces.md`,
> `../../../07-contracts/external-interfaces.md`.
> **Design-first note:** this specifies the **integration semantics and boundary**, not a concrete
> representation. No interface syntax, DTO types, or exception classes are introduced. Capability
> examples are **illustrative**, not a final internal capability catalog.

This is the contract this Backend documentation exists to preserve. It is an **internal capability
contract within the Modular Monolith — not a network/API contract or a separate-service API**. It is a
specific instance of the internal-contract style (`internal-contracts.md`), distinguished by being
collaboratively owned and by crossing to the Madar-owned LLM interface.

## What the Backend side specifies

- **The capabilities the Backend invokes** on the Learning & AI module. *Illustrative* examples:
  "generate a quiz from teacher-provided content," "recommend a State from relevant evidence." These
  are illustrative unless the capability catalog is already established by the domain/system knowledge.
- **Dependency direction:** `Backend → Learning & AI capability → Madar-owned LLM interface → external
  LLM` (where applicable). The external model stays **outside** the system boundary.
- **The trusted execution context** and applicable **tenant/enrollment scope** the Backend supplies
  (`../04-architecture/execution-model.md`, EX-1).
- **The bounded source input** supplied to the AI capability (e.g., the teacher-provided content for a
  quiz; the relevant evidence for a State recommendation).
- **Result and failure semantics**, including the established terminal operation states
  (`Submitted → Processing → Succeeded | Failed`) and no-partial-result guarantees where applicable
  (`../05-runtime/async-operations.md`; `../../../10-decisions/ADR-006-ai-async-failure-tolerant.md`).
- **Backend-owned persistence coordination** — the Backend coordinates persistence of AI product-state
  as Madar data; the LLM is never the source of truth (`../06-data/data-model.md`, DAT-3).
- **The Backend-side idempotency boundary** where idempotency is applicable
  (`../../../10-decisions/ADR-011-selective-idempotency.md`).

## What is deferred behind the seam (AI Module Documentation)

Everything behind this boundary is the responsibility of the Learning & AI module and is **out of
scope** for this Backend documentation: prompting strategy, model selection, RAG/retrieval internals,
ingestion/indexing internals, embeddings/chunking, AI algorithms, AI-specific orchestration internals,
and provider-specific AI implementation.

## Ownership and change control

| Concern | Owner |
|---------|-------|
| The integration contract & runtime integration boundary | Backend / Architecture |
| Backend-side integration of AI operations into the runtime | Backend / Architecture |
| Worker-side execution concerns at the Backend boundary | Backend / Architecture |
| Operation lifecycle coordination, context propagation, persistence coordination, idempotency boundary | Backend / Architecture |
| Internal implementation behind the contract | AI Engineer / Learning & AI module |
| AI internals (prompting, model, RAG, ingestion, embeddings, algorithms, provider specifics) | AI Engineer / Learning & AI module |

- The contract is **designed collaboratively**; both sides must agree on what is required at the
  boundary.
- **Neither side may unilaterally redefine or change the established contract.**
- Any change that would affect a **system-level** boundary, contract, invariant, ownership rule, or
  other established architectural truth must go through the **cross-level decision / escalation
  process** (`../README.md`) — it is not resolved locally.

## The KB seam is part of this boundary

The KB publish → processing orchestration boundary (`../01-scope/responsibilities.md`) follows the same
division: the Backend owns the application-level authoring/publish surface and the publish/processing
orchestration; the AI-specific indexing/retrieval implementation is behind this seam. The concrete KB
store technology remains Open and is not assigned to either side by this contract.

## The AI Module Documentation inherits this seam

The later AI Module Documentation starts from the System Documentation **and** this established
Backend/AI contract as its authoritative boundary, then specializes further into the AI Module itself.
It must not redefine this seam without escalation.
