# Data Model

> **Authority:** Descriptive (the model); the **scoping rule and integrity rules are Normative** and
> cross-referenced to the invariants/ADRs.
> **Source of truth** for the data representation of domain concepts.
> **Depends on:** `03-domain/`, ADR-004/007.
> **Scope note:** entities, keys, and integrity rules — not physical schema, index strategy, or ORM
> mechanics (deferred to implementation).
> **Diagram:** [`../diagrams/data/erd.mmd`](../diagrams/data/erd.mmd).

## Two-level scoping

| Level | Key | Purpose |
|-------|-----|---------|
| **Tenant / isolation** | `teacher_environment_id` | Universal key on **every** teacher-scoped record; the column the data-access isolation layer filters on (ADR-004/007/008). |
| **Ownership / relationship** | Enrollment | The relationship key for **enrollment-scoped** educational records (attendance, recitation, payment, state, rating, notes). |

These are intentionally distinct. Not all teacher-scoped entities belong to an Enrollment — Academic
Year, Grade, Group, Schedule, and video metadata exist at the Teacher-Environment level. So the
**universal** isolation key is `teacher_environment_id`, and Enrollment scopes records **within** it.

## Entities

**Global (not teacher-scoped):**
- **Student** — identity: name, phone/login, claim state. The only entity without
  `teacher_environment_id`. May be unclaimed; may have 0..* Enrollments.

**Teacher-Environment-scoped (carry `teacher_environment_id`):**
- **Academic Year**, **Grade** (owns fee), **Group** (belongs to a Grade), **Schedule** (Group slot),
  **Session Instance** (belongs to a Group; state machine), **Video metadata** (+ targeting + external
  reference), **Enrollment**.

**Enrollment-scoped (carry `teacher_environment_id` + belong to an Enrollment):**
- **Group membership**, **Attendance** (`Enrollment × Session Instance`), **Recitation** (`Enrollment
  × Session Instance`), **Payment** (`Enrollment × Month`), **State** (`Enrollment × Month`),
  **Rating** (`Enrollment × Month`), **Teacher Private Notes**.

**Other stored data:** Notification events, push registrations (device tokens), AI quizzes +
answers/scores. The central **Knowledge Base** is internal but held in its **own knowledge store**,
not ordinary transactional domain data.

## Grade context: derived, not stamped

Monthly records (Payment, State, Rating) do **not** store a duplicated `grade_id`. Their academic
(Grade) context is **derived from the Enrollment**, which is safe because Grade is immutable within an
Enrollment (INV-3). This avoids a redundant consistency invariant
(`record.grade_id == enrollment.grade_id`). See ADR-007 and `10-decisions/rejected-deferred.md`.

> Explicit stamping would only be reconsidered if Enrollment ever became mutable across Grades or
> historical records had to become independently self-contained. Neither is true in V1.

## Billing logical concepts (candidate; commercial model now decided, schema not)

> Recorded following the commercial-design pass (`01-product/commercial-model.md`,
> `10-decisions/ADR-014-billing-bounded-module.md`). These are **candidate logical concepts**, not a
> physical schema — fields, keys, and storage technology are an Implementation Plan concern, not
> decided here. **Do not conflate with the `Payment` entity above** (student→teacher fee tracking);
> these are the Teacher↔Madar commercial relationship, owned by the `billing` module.

- **Plan** — one of the three fixed paid tiers (price, 30-day period, student cap or none, feature
  set). Global/catalog data, not teacher-scoped.
- **Subscription** — the Teacher Account/Environment's current commercial state (trial or one of the
  three Plans), its current billing period, and its renewal/cancellation status. Scoped to the single
  Teacher Environment permanently owned by its Teacher Account (INV-9).
- **BillingPeriod** — a 30-elapsed-day cycle instance of a Subscription; never a calendar month.
- **Invoice / line items** — the record of what was owed for a BillingPeriod, where required.
- **PaymentAttempt** — one attempt to charge the Teacher for a BillingPeriod/Invoice, with an outcome
  (succeeded/failed/pending); distinct from, and may be many-to-one against, an Invoice.
- **Saved-payment-method / recurring-agreement reference** — a reference to the token/agreement Kashier
  returns after a successful initial setup, per Kashier's merchant-owned recurring-billing model; not a
  stored card number.
- **Provider event record** — a durable record of each verified inbound Kashier webhook event, used for
  provider-event deduplication (distinct from the existing client-request `idempotency_key` mechanism —
  `10-decisions/ADR-017-payment-event-idempotency.md`).
- **Entitlement/access decision** — the derived answer, at a point in time, to "does this Teacher
  currently have access, and to which plan-gated capabilities" — consumed by the access-decision
  boundary (`10-decisions/ADR-018-billing-entitlement-boundary.md`); not itself a stored ledger, though
  it may be informed by one.

**Relationships (to the extent the confirmed policies support — not further invented):** one Teacher
Environment has at most one active Subscription at a time; a Subscription has many BillingPeriods over
time; a BillingPeriod has zero-or-more PaymentAttempts and, where required, one Invoice; a verified
Provider event record may transition a PaymentAttempt/Invoice/Subscription's state, per the state
separation in ADR-017. No state-machine transition names are fixed here beyond what
`01-product/commercial-model.md` already states (trial → active-on-a-plan; auto-renew; cancel-at-
period-end; failed-renewal → limited retries → grace → access-not-granted, with exact numbers open).

## Negative space (referenced, not owned)

- **Video blob** — external storage; Madar stores metadata + targeting + an external reference.
- **LLM model knowledge/state** — never owned or persisted by Madar; LLM interactions are persisted
  only where their output becomes a meaningful Madar product result (a quiz, a score, an advisory
  State recommendation).
- **Push delivery** — external; Madar stores device tokens/registrations only.
