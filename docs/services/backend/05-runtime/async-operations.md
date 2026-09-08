# Backend Runtime — Canonical Async-Operation Spine

> **Authority:** Descriptive (canonical for the Backend async-operation runtime path).
> **Specializes:** `../../../05-runtime/ai-quiz.md`, `../../../05-runtime/state-pipeline.md`,
> `../../../07-contracts/api-contract.md`, `../../../10-decisions/ADR-006-ai-async-failure-tolerant.md`,
> `../../../10-decisions/ADR-011-selective-idempotency.md`.
> **Diagram:** `../diagrams/runtime/async-operation-spine.mmd`.

The system already models **AI Quiz** and **State recommendation** as asynchronous submit-then-poll
operations. This document specializes them into a single Backend runtime spine. It also records the
**Study Assistant** interaction model as explicitly Open/Deferred.

## The canonical spine (Quiz and State-recommendation)

For AI capabilities **explicitly modeled as client-facing asynchronous operations**, the Backend
runtime path is:

1. **Web/API** receives the operation submission.
2. Backend performs authentication, authorization, and server-derived context establishment.
3. The applicable **idempotency boundary** is enforced
   (`../../../10-decisions/ADR-011-selective-idempotency.md`) — a client retry does not create a
   duplicate operation.
4. Backend creates/persists the operation in its initial lifecycle state and establishes the
   **trusted operation execution context** (`../04-architecture/execution-model.md`, EX-1).
5. Backend acknowledges the submission with the **operation identifier**.
6. The **Worker** picks up the work and **reconstructs the trusted execution context** from
   server-created state/context; it never executes from client-derived or unscoped privileged context.
7. The operation transitions to `Processing`.
8. The Worker invokes the appropriate **Learning & AI** module capability, which may cross the
   established Backend-owned **LLM integration boundary**
   (`../07-contracts/backend-ai-integration-contract.md`).
9. Backend persists the operation **result or failure** and records the appropriate terminal state
   (`Succeeded` or `Failed`).
10. Where the established contract exposes polling, the client reads the operation state/result
    through the API.

```
Web submit
  → authn / authz / server-derived context
  → idempotency boundary
  → persist operation (initial state) + establish trusted operation context
  → acknowledge (operation id)
        │
        ▼   [Worker]
  reconstruct trusted context (never client-derived / unscoped-privileged)
  → Processing
  → invoke Learning & AI capability  → (Madar-owned LLM interface)
  → persist result | failure  → terminal Succeeded | Failed
        │
        ▼
Client polls → reads terminal state / result (where the contract exposes polling)
```

### What the spine standardizes — and what it does not

The spine is a **common runtime path**, not a requirement that all AI operations share identical
business semantics, result shapes, persistence models, or failure details. Per-operation differences
are only *what the capability does* and *what product-state is persisted* — not the runtime spine.

The relationship between the operation record and the trusted execution context is a
**runtime/behavioral concept, not an implementation prescription**. This documentation does not infer
any storage structure or mechanism — not embedding the context in the operation record, a separate
record, queue metadata, a signed payload, or any particular job/queue technology.

The spine applies to the AI operations the System Documentation already models as asynchronous
(**Quiz** and **State recommendation**), and to any other AI capability **only once its operation
model is explicitly established**.

## Per-operation instantiation (differences only)

- **AI Quiz** — student-initiated; source = teacher-provided content. On success: quiz persisted
  before the student answers → student answers → auto-scored where the question type allows → result
  persisted (student-visible). On failure/timeout: clear failure state + retry; **no partial/invalid
  quiz** persisted or presented (`../../../05-runtime/ai-quiz.md`).
- **State recommendation** — on-demand when the teacher reviews the student's month; produces an
  **advisory** recommendation. AI is never authoritative — the teacher accepts, modifies, or assigns
  the State directly, and the finalized State is the teacher's decision. On failure/timeout: no
  recommendation available; the teacher proceeds with manual finalization
  (`../../../05-runtime/state-pipeline.md`).

In both, AI failure never blocks or corrupts deterministic Madar data; AI product-state that
represents a result is persisted, and the LLM is never the source of truth
(`../../../10-decisions/ADR-006-ai-async-failure-tolerant.md`; persistence facts in
`../06-data/data-model.md`).

## Study Assistant — interaction model Open/Deferred

The **AI Study Assistant** is currently described at system level as a capability **without** an
explicit runtime interaction/lifecycle model. This documentation therefore records it as
**Open/Deferred** and does **not** assume it follows the submit→poll spine merely because Quiz and
State recommendation do.

No operation lifecycle, polling contract, synchronous interaction pattern, or other runtime behavior
is introduced for the Study Assistant here.

> **Forward constraints (for whoever resolves it).** When the Study Assistant interaction model is
> established by the appropriate system/product/AI design work, it must remain consistent with the
> Backend ↔ AI boundary, the authorization and tenant-isolation guarantees, invariant enforcement, and
> the applicable async execution/failure principles. **If the eventual interaction model would change
> an established system contract or boundary, it must be escalated** rather than silently redefined
> (`../README.md`).
