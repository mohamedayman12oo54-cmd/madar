# Data — Consistency & Integrity

> **Authority:** **Normative** (integrity rules).
> **Depends on:** ADR-005, ADR-006; `03-domain/invariants.md`.

## Transactional record + event

For automatic notifications (Absent, Not-Studied), the **core record change and the notification
event are created in the same transaction**. Example: an Absent attendance record and its Absent
notification event commit atomically. Only **after** commit does the asynchronous consumer attempt
delivery. This closes the "record persisted but event lost" gap between the write and event creation
(ADR-005). **Delivery** itself remains asynchronous and may fail independently.

## AI outputs as product state

AI outputs that represent product state are **persisted**; the LLM interaction is never the source of
truth (ADR-006):

- Generated quizzes are persisted **before** the student answers.
- Student answers and scoring results are persisted as educational records.
- State recommendations are persisted as **advisory** results; the finalized State is the teacher's.

AI persistence/failure must never partially corrupt or block deterministic Madar state. A failed AI
operation yields no partial product state (no partial/invalid quiz).

## Tenant-scope integrity

Every teacher-scoped write and read is constrained by the established tenant context
(`teacher_environment_id`) at the data-access boundary; modules cannot bypass this on the normal path
(ADR-004/007). The Student identity is the only entity outside tenant scope.

## Invariant preservation at the data layer

The data model must uphold the domain invariants (`03-domain/invariants.md`), in particular:
one Enrollment per (Student × Teacher-Env × Year) (INV-2), one immutable Grade per Enrollment (INV-3),
Group membership within the Enrollment's Grade (INV-4), Grade-owned fee (INV-5), preserved historical
context via Enrollment-derived Grade (INV-6), and record–session association (INV-8).
