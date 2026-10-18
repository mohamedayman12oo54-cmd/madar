# API Contract

> **Authority:** **Normative.** All clients (Teacher, Student, Content Maintainer) and all future
> service documentation MUST comply. No client or module may redefine these rules.
> **Source of truth** for the internal API's shaping rules and semantics.
> **Depends on:** the architecture decisions (ADR-003/004/006/008/010/011) and the domain model.
> **Scope note:** this document defines the **contract rules** (style, tenant semantics, async model,
> error contract, versioning). Concrete endpoint catalogs and serialized schemas are produced later
> in the API documentation stage and are deliberately **not** invented here.

## Style

- **REST**, single unified API surface for all three clients — [ADR-003](../10-decisions/ADR-003-unified-api-surface.md).
- **Versioned from V1:** `/api/v1/...`. A full deprecation / backward-compatibility policy is
  deferred; the version namespace exists from day one.
- Different clients may have different allowed operations and response shapes, but they are all
  consumers of the **same** API boundary — not separate API products.

## Tenant context (the isolation rule)

This is the contract-level teeth of the system's highest-priority quality attribute.

- `teacher_environment_id` is **never** accepted as an arbitrary, client-controlled tenant selector.
- On each request, the server: authenticates the actor → resolves them against the environments they
  are **authorized** to access → establishes the active Teacher-Environment context **server-side**.
- A client may **explicitly switch** to an environment it is authorized to access, but it cannot
  choose an arbitrary tenant ID and thereby control isolation.
- The established context is then enforced at the data-access boundary
  ([ADR-004](../10-decisions/ADR-004-two-layer-tenant-isolation.md) /
  [ADR-007](../10-decisions/ADR-007-two-level-data-scoping.md)).

See [ADR-008](../10-decisions/ADR-008-server-derived-tenant-context.md).

## Multi-teacher student scope

A student may have Enrollments under multiple Teacher Environments, but:

- A student-facing API session/context operates within **one active Teacher Environment at a time**.
- Switching from Teacher A to Teacher B is an **explicit context switch** to an environment the
  student holds an authorized Enrollment in.
- The API does **not** return cross-environment educational data for the client to merge. Every
  response and operation is scoped to the active environment.

This makes tenant isolation a **contract rule**, not a client-side responsibility.

## Authorization

Every authorization decision combines: **authenticated actor + role + authorized environment +
relationship/ownership scope.** Role alone is never sufficient —
[ADR-010](../10-decisions/ADR-010-composite-authorization.md).

- **Teacher** — operates only within their authorized environment and its records.
- **Student** — operates within one active authorized environment; can access only records belonging
  to their own Enrollment there.
- **Content Maintainer** — limited to the central content/KB surface; has **no** access to teacher
  educational records.

## Asynchronous operations

AI Quiz generation and State recommendation are **asynchronous** — modeled as submit-then-retrieve,
not synchronous calls with a long timeout ([ADR-006](../10-decisions/ADR-006-ai-async-failure-tolerant.md)).

- **Submit** → the API acknowledges with an **operation identifier**.
- **Retrieve** → the client polls operation status/result. Streaming/real-time subscription is **not**
  required in V1; polling is the initial contract.
- **States:** `Submitted → Processing → Succeeded | Failed`.
- **Failures are explicit and machine-readable:**
  - *Quiz generation failure* → no usable/partial quiz is persisted; the student may retry.
  - *State recommendation failure* → no recommendation available; the teacher proceeds with manual
    finalization.
  - AI failure never blocks or corrupts deterministic Madar data.
- **Idempotency:** retryable AI operation submission is idempotent, so a client retry does not create
  duplicate operations — [ADR-011](../10-decisions/ADR-011-selective-idempotency.md). Idempotency is
  **selective**, not universal across the API.

## Error & validation contract

One consistent error contract across all clients. Errors expose **stable, machine-readable codes** and
structured semantics — not endpoint-specific formats. Human-readable messages are kept **separate**
from the stable client-facing codes.

The contract covers at least:

| Category | Examples |
|----------|----------|
| Authentication / authorization | not authenticated, not authorized |
| Tenant / context violation | attempt to act outside the active/authorized environment |
| Validation | malformed or invalid input |
| Not found | resource does not exist within scope |
| Business-rule / conflict | violates a domain rule or an invariant |
| Service / internal | unexpected failure |

The exact serialized schema (field names, envelope shape) is deferred to the API documentation stage.

## What this contract deliberately does not include (V1)

No SMS/WhatsApp/email; no teacher-published quiz; no streaming async transport; no per-client separate
APIs. These are recorded as negative space so a future implementer does not assume them.

**Payment/billing endpoints — scoped exception, not a general opening.** Following the
commercial-design pass, Madar now has online-payment/billing endpoints (checkout initiation, billing
status) and exactly **one** inbound external integration — the signature-verified Kashier
payment-result webhook, approved narrowly by
[ADR-016](../10-decisions/ADR-016-inbound-webhook-exception.md). This is **not** a general reopening of
"no inbound third-party integrations": every other inbound integration remains out of scope for V1
unless and until it receives its own dedicated ADR. The webhook endpoint, its signature-verification
requirement, and its separation from ordinary outbound/redirect traffic are detailed in
`external-interfaces.md`. No endpoint catalog or serialized schema for billing is defined here — that
remains deferred to the API-documentation stage, consistent with this document's scope note.
