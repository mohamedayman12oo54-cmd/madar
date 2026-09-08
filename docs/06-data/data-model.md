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

## Negative space (referenced, not owned)

- **Video blob** — external storage; Madar stores metadata + targeting + an external reference.
- **LLM model knowledge/state** — never owned or persisted by Madar; LLM interactions are persisted
  only where their output becomes a meaningful Madar product result (a quiz, a score, an advisory
  State recommendation).
- **Push delivery** — external; Madar stores device tokens/registrations only.
