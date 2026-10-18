# Backend Data Model — Data-Behavior & Integrity

> **Authority:** Descriptive (the model); the **scoping and integrity rules are Normative** and
> cross-referenced to the inherited invariants/ADRs.
> **Specializes:** `../../../06-data/data-model.md`, `../../../06-data/consistency.md`,
> `../../../06-data/lifecycle-retention.md`, `../../../10-decisions/ADR-004-two-layer-tenant-isolation.md`,
> `../../../10-decisions/ADR-007-two-level-data-scoping.md`.
> **Diagram:** `../diagrams/data/backend-erd.mmd`.
> **Scope note:** this is a **logical/documentational** data-behavior model — entities, scoping tiers,
> keys, derived context, and integrity rules. It does **not** define physical schema, index strategy,
> ORM mechanics, storage technology, or resolve the still-open AI product-state persistence ownership.
> Those remain Open.

The System data model, two-level scoping, derived-Grade context, and integrity rules are **binding and
inherited**. This document specializes them into the Backend's data-behavior and integrity model.

## Two-level scoping (inherited, specialized)

| Level | Key | Purpose |
|-------|-----|---------|
| **Tenant / isolation** | `teacher_environment_id` | The universal isolation attribute on **every** teacher-scoped record; the attribute the data-access isolation layer filters on. |
| **Ownership / relationship** | Enrollment | The relationship key for **enrollment-scoped** educational records. |

### DAT-1 — `teacher_environment_id` is a uniform structural isolation attribute, not a shared-ownership model

Every teacher-environment-scoped record across all module persistence carries
`teacher_environment_id`, and the data-access boundary enforces filtering/isolation by the
**server-derived** environment context (`../../../10-decisions/ADR-008-server-derived-tenant-context.md`).

This does **not** imply shared persistence ownership. Each module continues to own its **private
persistence** and must not directly read or write another module's persistence
(`../03-internal-boundaries/module-boundaries.md`, BND-1). The shared `teacher_environment_id` is a
**cross-cutting structural isolation guarantee**, not a shared data-ownership model. The concrete
enforcement mechanism (ORM/repository/database-level mechanism) remains **Open**.

## Entities and scoping tiers (inherited)

- **Global (not teacher-scoped):** **Student** — the only entity without `teacher_environment_id`;
  identity (name, phone/login, claim state); may be unclaimed; may have 0..* Enrollments.
- **Teacher-Environment-scoped** (carry `teacher_environment_id`): Academic Year, Grade (owns fee),
  Group (belongs to a Grade), Schedule, Session Instance (state machine), Video metadata, Enrollment.
- **Enrollment-scoped** (carry `teacher_environment_id` + belong to an Enrollment): Group membership,
  Attendance (`Enrollment × Session Instance`), Recitation (`Enrollment × Session Instance`), Payment
  (`Enrollment × Month`), State (`Enrollment × Month`), Rating (`Enrollment × Month`), Teacher Private
  Notes.
- **Other stored data:** notification events / durable event hand-offs, push registrations (device
  tokens), AI product-state (see DAT-3).

## DAT-2 — Grade context is derived, not stamped

Monthly records (Payment, State, Rating) do **not** store a duplicated `grade_id`. Their academic
(Grade) context is **derived from the Enrollment**, which is safe because Grade is immutable within an
Enrollment (INV-3/INV-6). This avoids a redundant consistency invariant. The Backend upholds this by
resolving academic context through the Enrollment (via the Identity & Enrollment capability), never by
stamping a redundant key.

## Knowledge Base — application-level lifecycle; store technology Open

- KB content has an **application-level authoritative lifecycle/state owned by the Backend**
  (`../01-scope/responsibilities.md`, the KB seam).
- The KB is held in a **separate knowledge store** from ordinary transactional data — a statement of
  *separateness*, consistent with the system's data model.
- The **concrete KB storage technology/mechanism remains Open**. No physical storage ownership or
  implementation detail is inferred beyond the established application-level ownership and lifecycle
  responsibilities.

## DAT-3 — AI product-state: persisted as Madar data; persistence ownership Open

Product-state produced through AI capabilities (generated quizzes, answers/scores, advisory State
recommendations) is **persisted as Madar product data**; the LLM is **never** the source of truth
(`../../../10-decisions/ADR-006-ai-async-failure-tolerant.md`, `../../../06-data/consistency.md`).

> **Open item — not resolved here.** This documentation does **not** infer that the AI Module owns
> persistence for all AI-related product-state merely because the state is AI-generated. Persistence
> ownership remains **Open** wherever it has not already been established by the domain/building-block
> decomposition, and is to be resolved only where required — routed to the **AI Module / Domain
> refinement**, not resolved implicitly at the Data stage. See `../11-validation/open-items.md`.

## DAT-4 — Teacher account, Environment lifecycle, and access state (from the upstream lifecycle correction)

The System Documentation's lifecycle-correction pass makes explicit concepts the Backend data model
previously left implicit. These are recorded at the **logical** level, each justified by a System-level
behavior, with mechanisms fenced. No physical schema, table, field, or storage technology is chosen.

- **Teacher account / actor.** The Teacher is a Madar **account holder** — a distinct, authenticatable
  actor (`../../../03-domain/actor-lifecycles.md`; `../01-scope/teacher-access-lifecycle.md`, TAL-1).
  The Backend logically represents a Teacher account as the authenticatable actor associated with a
  Teacher Environment. Whether this is a new persisted concept or realized through existing
  actor/identity representation is an **implementation concern**; the authentication **mechanism is
  fenced**.
- **Teacher ↔ Environment relationship & Environment origin.** An Environment is **established** in
  association with the Teacher and begins **empty** (TAL-2). Logically this implies a **Teacher ↔
  Environment association** and recognition of an Environment's **established/initial** state.
  **Cardinality is now resolved**: exactly one Environment per Teacher Account, permanently (INV-9,
  `../../../10-decisions/ADR-013-permanent-environment-cardinality.md`). The **provisioning trigger**
  mechanism remains **fenced**.
- **Access state.** The Teacher's **trial/subscription access state** governs *whether* access is
  currently granted (TAL-5). Logically this is an **access-state attribute/association of the Teacher
  (or Teacher↔Madar relationship)**, now realized concretely as the Subscription/Entitlement concepts
  owned by the **Billing** module (`../../../10-decisions/ADR-014-billing-bounded-module.md`; see
  DAT-5 below) and consumed by the access-decision boundary
  (`../../../10-decisions/ADR-018-billing-entitlement-boundary.md`). Pricing, plan definitions, trial
  parameters, and billing-cycle mechanics are decided
  (`../../../01-product/commercial-model.md`); exact access-not-granted behavior, refunds, and
  proration remain **fenced**. It is **distinct from** student fee tracking (Payment:
  `Enrollment × Month`), which is unchanged.

## DAT-5 — Billing logical concepts (candidate; owned by the `billing` module)

Following the commercial-design pass, the **Billing** module
(`../../../10-decisions/ADR-014-billing-bounded-module.md`) logically owns its own private persistence,
per BND-1, for: Plan (catalog), Subscription (one per Teacher Environment, consistent with INV-9),
BillingPeriod (30-elapsed-day cycles, never calendar-month), Invoice/line items where required,
PaymentAttempt, saved-payment-method/recurring-agreement reference, provider event record (for
provider-event dedup — distinct from the AI module's client-request `idempotency_key`, per
`../../../10-decisions/ADR-017-payment-event-idempotency.md`), and the derived entitlement/access
decision. These are **candidate logical concepts** per
`../../../06-data/data-model.md` §Billing logical concepts — no physical schema, migration, or
field list is fixed here; that is an Implementation Plan concern. Other modules obtain Billing-owned
information (e.g., "is this Environment's access currently granted") only through an explicit internal
capability exposed by Billing, consistent with BND-1 — never by reading Billing's persistence
directly.

> **No entities added by inference.** These concepts are named because an authoritative System-level
> behavior requires them, not because they seem technically useful. Their concrete representation
> (new entities vs. attributes on existing ones), keys, and storage remain **Open** — consistent with
> the design-first, stack-Open stance and the fenced mechanisms above.

## Integrity rules (inherited, upheld by the Backend)

- **Transactional record + event.** For automatic notifications (Absent, Not-Studied), the core record
  change and the durable notification event hand-off are created in the same transaction, within the
  emitting module's boundary; delivery is asynchronous and may fail independently
  (`../../../06-data/consistency.md`; `../05-runtime/fast-session.md`).
- **AI product-state as product state.** Persisted where the output becomes a meaningful Madar result;
  a failed AI operation yields no partial product state (no partial/invalid quiz).
- **Tenant-scope integrity.** Every teacher-scoped write and read is constrained by the established
  tenant context at the data-access boundary; modules cannot bypass this on any applicable path. The
  Student identity is the only entity outside tenant scope.
- **Invariant preservation.** The data behavior upholds the domain invariants (INV-2/3/4/5/6/8);
  invariant enforcement is a hard, all-paths guarantee (`../02-requirements/backend-requirements.md`,
  BR-1).

## Negative space (referenced, not owned)

- **Video blob** — external storage; the Backend stores metadata + targeting + an external reference.
- **LLM model knowledge/state** — never owned or persisted by the Backend; LLM interactions are
  persisted only where their output becomes a meaningful Madar product result.
- **Push delivery** — external; the Backend stores device tokens/registrations only.
