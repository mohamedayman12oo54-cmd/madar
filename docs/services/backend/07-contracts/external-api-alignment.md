# External API Alignment

> **Authority:** References + Specializes. The **external / client-facing API contract is Normative
> upstream** (`../../../07-contracts/api-contract.md`) and is **not redefined here**.
> **Specializes:** `../../../07-contracts/api-contract.md`,
> `../../../10-decisions/ADR-003-unified-api-surface.md`,
> `../../../10-decisions/ADR-008-server-derived-tenant-context.md`,
> `../../../10-decisions/ADR-010-composite-authorization.md`.
> **Design-first note:** the exact serialized error taxonomy, HTTP status selection where not already
> established, error codes/categories, JSON/error payload schemas, endpoint-specific representations,
> and the endpoint catalog are **deferred to the later API-documentation stage** and are **not**
> invented here.

The Backend serves the single unified, versioned REST API for all three clients. The contract rules —
REST style, `/api/v1`, server-derived tenant context, one active environment per student-facing
context, composite authorization, submit-then-poll async model, selective idempotency, and the uniform
error contract — are **binding and inherited** from `../../../07-contracts/api-contract.md`. This document
records only how the Backend aligns to that contract and the one **new** assertion it makes: the
semantic failure mapping.

## Inherited contract rules (referenced, not restated)

- **Style & versioning** — REST, single unified surface, `/api/v1` (`ADR-003`).
- **Tenant context** — `teacher_environment_id` is never a client-controlled selector; established
  server-side; enforced at the data-access boundary (`ADR-008`, `ADR-004`/`ADR-007`).
- **Multi-teacher scope** — one active Teacher Environment per student-facing context; no
  cross-environment merge.
- **Authorization** — composite: actor + role + authorized environment + relationship/ownership
  (`ADR-010`).
- **Async operations** — submit → operation id → poll; `Submitted → Processing → Succeeded | Failed`;
  selective idempotency (`ADR-006`, `ADR-011`).
- **Error & validation contract** — one consistent error contract; stable machine-readable codes;
  human-readable messages separate from codes.

## AL-2 — Lifecycle preconditions to the contract (from the upstream lifecycle correction)

The contract's "authenticated actor + authorized environment" assumption has explicit **upstream
preconditions** now that the System Documentation documents Teacher entry and access
(`../../../03-domain/actor-lifecycles.md`, `../../../01-product/access-lifecycle.md`). These are
recorded as boundary consequences, not as new endpoint or schema design:

- **Teacher authentication precedes the contract.** A Teacher request presupposes an **authenticated
  Teacher actor**; producing that authenticated context is a Backend responsibility (TAL-1,
  `../01-scope/teacher-access-lifecycle.md`). The authentication **mechanism is fenced** — no
  credential/OTP/token/provider choice is made here.
- **Environment availability is a lifecycle state.** The "authorized environment" a request targets is
  one that has been **established** and may begin **empty** (TAL-2); the contract does not assume an
  Environment is always pre-existing and populated. Provisioning trigger and per-Teacher cardinality
  remain **fenced**; the existing "one *active* environment per student-facing context" rule is
  unchanged.
- **Access state may gate operations.** Whether a Teacher currently **has access** (Free Trial /
  Subscription) is an abstract input to the access decision (TAL-5), **separate from and prior to**
  composite authorization. Whether an access-not-granted condition surfaces as a distinct
  client-facing outcome, and its exact semantics, are **fenced** (commercial mechanics and
  access-not-granted behavior are unresolved upstream). No billing/entitlement API is designed here.

No signup, billing, invitation, or provisioning endpoints are defined by these consequences — only the
recognition that the existing contract's preconditions are now explicit. Endpoint/schema detail
remains deferred to the API-documentation stage.

## AL-1 — Semantic internal→external failure mapping (asserted); wire-level mapping deferred

The Backend asserts the **behavioral/semantic** mapping between internal failures and the established
client-facing operation/request semantics. It does **not** invent the serialized error taxonomy.

**Semantic guarantees (asserted):**

- A domain/invariant **rejection remains a rejection** — it must not be silently converted into
  success (`../02-requirements/backend-requirements.md`, BR-1).
- A client-facing asynchronous operation that fails reaches its established terminal **`Failed`** state.
- Established **no-partial-result** guarantees remain intact (e.g., no partial/invalid quiz).
- Internal capability failures **must not bypass** the established authorization, tenant-isolation, or
  invariant semantics.
- When an internal failure is surfaced through a client-facing boundary, it **honors the existing
  uniform client-facing error/operation semantics**.

**Deferred to the API-documentation stage (not invented here):**

- exact HTTP status selection where not already established;
- exact error codes / categories;
- JSON / error payload schemas;
- endpoint-specific serialized representations;
- any new error taxonomy.

## What this document deliberately does not include

No endpoint catalog and no serialized schema — those belong to the later API-documentation stage, per
the inherited contract's own scope note. Recording this as negative space prevents a future
implementer from assuming they exist here.
