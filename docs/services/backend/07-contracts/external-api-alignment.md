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
  Environment is always pre-existing and populated. **Cardinality is resolved** — exactly one
  Environment per Teacher Account, permanently (ADR-013/INV-9); only the provisioning **trigger**
  mechanism remains fenced. The existing "one *active* environment per student-facing context" rule is
  unchanged.
- **Access state may gate operations.** Whether a Teacher currently **has access** (Free Trial /
  Subscription) is an input to the access decision (TAL-5), owned by the Billing module and consumed
  **separate from and prior to** composite authorization (ADR-018). Commercial parameters are now
  decided (`../../../01-product/commercial-model.md`); the exact client-facing surfacing of an
  access-not-granted condition and its precise semantics remain **fenced**. No billing/entitlement
  endpoint catalog is designed here — see AL-3 for the trust-boundary distinctions that **are**
  asserted.

No signup, billing, invitation, or provisioning endpoints are defined by these consequences — only the
recognition that the existing contract's preconditions are now explicit. Endpoint/schema detail
remains deferred to the API-documentation stage.

## AL-3 — Payment trust-boundary distinctions (from the commercial-design pass)

Following the commercial-design pass and `../../../10-decisions/ADR-016-inbound-webhook-exception.md`,
the Backend asserts these trust-boundary distinctions explicitly, so a future implementer does not
conflate them:

- **Outbound calls to Kashier** (checkout initiation, status lookup) — ordinary outbound usage of the
  payment-provider interface, the same shape as the LLM/Push/Video interfaces.
- **Inbound, signature-verified Kashier webhook events** — the system's **one** approved inbound
  external integration. Only a verified webhook event (or an internal reconciliation job polling
  Kashier's own status API) may transition Subscription/Invoice/PaymentAttempt state.
- **Browser return/redirect URLs** — carry **no trust weight**. A redirect must never independently
  activate a subscription or any paid capability.
- **Internal billing-state transitions** — occur only as a consequence of the two trusted paths above,
  never from an unauthenticated inbound signal of any other kind.

**Payment-event safety is distinct from the existing AI client-request idempotency mechanism.**
`ai/models.py`'s `idempotency_key` (`../../../10-decisions/ADR-011-selective-idempotency.md`) prevents
a **calling user's own retry** from creating a duplicate AI operation; it is **not** a substitute for
provider-event deduplication, signature verification, or replay protection, which a payment webhook
requires and which are a **new**, separate mechanism per
`../../../10-decisions/ADR-017-payment-event-idempotency.md`. A webhook **arriving** is not, by itself,
proof of a successful payment.

## AL-4 — Future Frontend contract needs around Billing (noted, not designed)

The following Frontend contract needs are anticipated around the Billing module and are recorded here
for future coordination; **no endpoint, schema, or UI is designed by this note**:

- Plan discovery (listing the three plans and their prices/caps/features).
- Subscription/trial state (current plan, trial-days-remaining, billing-period end).
- Checkout initiation (handing off to Kashier's hosted flow) and payment confirmation/pending states.
- Billing status/history (past periods, invoices where applicable).
- Renewal/cancellation status (next renewal date, cancellation-takes-effect-at-period-end messaging).
- Restricted-access/recovery UI (what a Teacher sees and can still do once access is not granted).
- Student-count-limit responses (what happens when a plan/trial cap is reached).
- AI-feature-availability/quota responses (which AI capability a Teacher's current plan unlocks).

**Separately, frontend-owned, out of Backend scope:** `apps/web/src/lib/financialsApi.js` references
non-existent backend routes (`/financials/payments/`, `/financials/summary/`) and remains unused/dead
code (per the Kashier readiness audits). This is a Frontend cleanup item, noted here for awareness
only — not fixed by this Backend documentation pass.

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
