# Validation — Traceability

> **Authority:** Descriptive (documentation quality control, not system knowledge).
> **Purpose:** show that the major decisions trace coherently from product need to implementation
> constraint. These chains were validated before documentation and are recorded here for review.

## Tenant isolation chain

```
Product: multi-teacher student usage (committed V1)
  → Domain: global Student + teacher-scoped Enrollment; INV-7 isolation
  → Data: teacher_environment_id as universal tenant key (ADR-007)
  → Contracts: server-derived, non-client-controllable tenant context (ADR-008); one active env
  → Cross-cutting: composite authorization (ADR-010)
  → Architecture: two-layer enforcement (ADR-004)
```
One coherent thread; no divergence.

## Fast-session chain

```
Architecture driver #2: fast-session responsiveness
  → Runtime: per-tap persistence; UI advances immediately; async notify (05-runtime/fast-session.md)
  → Data: record + notification event committed transactionally (ADR-005)
  → Operations: web/worker split isolates dispatch from the write path (ADR-012)
```

## AI chain

```
Product: AI is advisory / never authoritative
  → Runtime: async, failure-tolerant (State pipeline, AI Quiz)
  → Data: AI product-state persisted; LLM not source of truth (ADR-006)
  → Contracts: submit → operation-id → poll; explicit failure; selective idempotency (ADR-011)
```

## Structural spine (cross-checked)

Grade owns fee / Group owns sessions — consistent across Requirements (INV-5), Domain, and Data.
Session Instance is first-class across Domain, Runtime, and Data.
