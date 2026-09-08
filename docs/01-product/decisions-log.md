# Product Decisions Log

> **Authority:** Normative (records product-level decisions and their provenance).
> **Source of truth** for product decisions that refined or superseded the original brief.
> **Depends on:** `product.md`, `scope.md`.
> **Scope note:** this log covers **product-level** decisions. Architecturally significant decisions
> live as ADRs in [`../10-decisions/`](../10-decisions/README.md); this file does not restate them.

This log preserves *why* the V1 product looks the way it does — specifically where a deliberate
product decision **changed the meaning** of something in the original project brief. Each entry is an
intentional decision, not an unresolved ambiguity.

## PD-1 — AI Study Assistant redefined as a general tutor

- **Brief said:** the AI assistant is tied to the content/context available to the individual student.
- **Decision:** the AI Study Assistant is a **general educational tutor** grounded in the central,
  product-owned curated Knowledge Base, with a bounded source/input contract. It is **not** scoped to
  the individual student's records or identity in V1, and need not understand the student's complete
  Madar domain context.
- **Status:** intentional supersession of the brief.
- **Consequence:** teachers do **not** curate AI sources in V1; a central KB is a product-owned asset
  (introduces the Content Maintainer actor and the KB lifecycle). The AI Quiz, by contrast, uses
  **teacher-provided** content — a separate bounded source. See `scope.md` (AI boundaries),
  `../09-operations/knowledge-base.md`.

## PD-2 — Grade owns the monthly fee (not the Group)

- **Brief implied:** the Group carried the fee/schedule.
- **Decision:** the **Grade** owns the monthly fee. Groups within a Grade share the same fee; a
  student attending a second Group in the same Grade incurs **no** additional obligation.
- **Status:** correction of the brief's implied model.
- **Consequence:** payment scope is `Enrollment × Calendar Month` with Grade-owned fee. Group becomes
  purely a teaching/session unit. Canonical rule: `../03-domain/invariants.md` (INV-5).

## PD-3 — Multi-teacher student usage is committed V1

- **Brief framing:** data "isolated between teachers"; a single-teacher scope was implied.
- **Decision:** a real student may **actively** use Madar with multiple teachers in V1, switching
  between strictly isolated environments. Student **identity** may be global; **records** remain
  teacher-scoped. Isolation applies at the relationship-and-records level, not the identity level.
- **Status:** intentional refinement of the brief.
- **Consequence:** global Student identity + teacher-scoped Enrollment (the domain keystone); one
  active environment per API context. Canonical rules: `../03-domain/invariants.md` (INV-7) and
  `../07-contracts/api-contract.md` (multi-teacher scope). Enforcement: ADR-008.

## PD-4 — "New quiz/activity" notification removed

- **Brief listed:** a "new quiz/activity" notification event.
- **Decision:** **removed** — it contradicted the committed **student-initiated** AI-Quiz model.
  There is no teacher-published quiz in V1 and no "new quiz available" notification.
- **Status:** contradiction caught and resolved during discovery.
- **Consequence:** the V1 notification catalog is bounded to five events (Absent, Not-Studied, New
  video, Monthly rating published, Teacher manual broadcast). See
  `../02-requirements/functional.md` (Notifications).

## PD-5 — Homework fenced from the V1 Definition-of-Done

- **Brief listed:** homework upload/annotation among candidate capabilities.
- **Decision:** homework is **feasibility-dependent** and explicitly **outside** the V1
  Definition-of-Done. Its go/no-go is decided at the Requirements/feasibility phase; if it fails, V1
  is still complete.
- **Status:** intentional scope fence.
- **Consequence:** no committed V1 requirement depends on homework. See `scope.md` (The Homework
  fence).

---

These decisions are consolidated (alongside rejected/deferred architectural items) in
[`../10-decisions/rejected-deferred.md`](../10-decisions/rejected-deferred.md) under "Product
decisions that superseded the original brief."
