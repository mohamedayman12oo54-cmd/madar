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

## Billing / Kashier chain (added after the commercial-design pass)

```
Product: commercial-design pass confirms plans/trial/renewal/failed-payment-policy direction
  → Commercial model: 01-product/commercial-model.md (prices, caps, 16-day trial, 30-day period)
  → Domain: INV-9 permanent one-Environment-per-Teacher-Account cardinality (ADR-013)
  → Architecture: Billing as an eighth bounded Backend module (ADR-014)
  → Contracts: Madar-owned payment-provider interface / Kashier adapter (ADR-015);
               narrow inbound-webhook exception to outbound-only (ADR-016);
               external-interfaces.md / api-contract.md / system-context.mmd updated to match
  → Cross-cutting: payment-event integrity distinct from AI client-request idempotency (ADR-017);
                    billing-owned entitlement boundary, integrated with composite authz (ADR-018)
  → Data: candidate Billing logical concepts (06-data/data-model.md), distinct from financials/Payment
  → Backend specialization: services/backend/{01-scope,06-data,07-contracts,08-cross-cutting,
    09-operations,10-decisions,11-validation}/* and implementation-plan/* (cardinality items resolved)
  → Remaining open (by design, not oversight): retry/grace numbers, student-facing restricted-access
    behavior, refunds, proration, 30-day-vs-Kashier-recurring-interval compatibility, production
    scheduling — see 01-product/commercial-model.md §Open items.
```
Evidence base: `KASHIER_BACKEND_READINESS_AUDIT.md`, `KASHIER_SUPPLEMENTARY_AUDIT.md` (repo root,
read-only audits; not themselves part of this traceability chain's authoritative docs).

## Structural spine (cross-checked)

Grade owns fee / Group owns sessions — consistent across Requirements (INV-5), Domain, and Data.
Session Instance is first-class across Domain, Runtime, and Data.
