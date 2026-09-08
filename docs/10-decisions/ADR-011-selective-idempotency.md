# ADR-011 — Selective Idempotency for Retryable External/Stateful Commands

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
AI operations are async submit-then-poll (ADR-006) and depend on a costly external LLM. A client retry (e.g., after a flaky network) could otherwise create duplicate AI operations. Universal idempotency across every endpoint would add unnecessary complexity.

## Decision
Apply idempotency **selectively**: required for retryable commands where duplication is costly or stateful — **especially AI operation submission** — so a retry does not create duplicate operations. It is **not** universal across the API.

## Alternatives considered
- **Universal idempotency** — rejected: unnecessary complexity for simple, naturally-safe operations.
- **No idempotency** — rejected: client retries could spawn duplicate, costly AI operations.

## Consequences
- A client retry cannot spawn duplicate AI operations.
- The rest of the API stays simple.
- Targeted abuse/cost protection may layer onto the same externally-dependent operations if needed.
