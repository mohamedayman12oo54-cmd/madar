# ADR-006 — AI Operations Are Asynchronous and Failure-Tolerant

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
AI Quiz generation and State recommendation depend on an external LLM. A core product principle is that AI must never compromise deterministic product correctness, and AI latency ranks below fast-session responsiveness.

## Decision
AI Quiz generation and State recommendation are **asynchronous** operations (submit → operation id → poll status/result; states `Submitted → Processing → Succeeded | Failed`). AI outputs that represent product state are **persisted** (generated quizzes before the student answers; answers/scores; advisory State recommendations); the LLM interaction is never the source of truth. On failure: quiz generation yields **no** partial/invalid quiz and the student may retry; State recommendation simply becomes unavailable and the teacher finalizes manually.

## Alternatives considered
- **Synchronous AI with a long timeout** — rejected: couples user requests to LLM latency and risks hanging requests.
- **Streaming/real-time subscription** — deferred: not required in V1; polling is sufficient.

## Consequences
- Deterministic Madar data and teacher authority are independent of AI availability.
- Failures are explicit and machine-readable in the contract.
- Requires selective idempotency on AI submission (ADR-011) and background execution (ADR-012).
