# Domain Model

> **Authority:** Descriptive (the model) — but note that **`invariants.md` is Normative**.
> **Source of truth** for domain concepts, ownership, and relationships.
> **Depends on:** `00-overview/glossary.md` (uses its vocabulary).
> **Framework-independence:** this model is expressed without reference to any database, framework,
> or API. It is the world Madar represents.

## The structural spine

One distinction organizes the whole model:

- **Grade** is the **academic and financial** unit — it owns the monthly fee and scopes evaluation.
- **Group** is purely the **teaching/session organization** unit — it owns no fee.

Fee, Payment, State, Rating, and the one-Grade rule all key off **Grade**. Only attendance and
recitation key off **Group** (through a Session Instance). This is the central theme of the model.

## Identity vs. relationship

Madar separates a **global student identity** from the **teacher-scoped relationship**:

- **Student** = global identity (name, phone/login, claim state). Independent of any teacher. The
  same real student may have relationships with multiple teachers.
- **Enrollment** = the teacher-scoped relationship `Student × Teacher Environment × Academic Year`.
  It owns everything teacher-specific about that student for that year.

This is what makes **multi-teacher usage** work while keeping each teacher's records strictly
isolated: Teacher B never sees Teacher A's Enrollment records for the same global Student.

## Ownership tree

```
Student (GLOBAL identity — not teacher-scoped)
  • name, phone/login, claim state
  • may be unclaimed; may have 0..* Enrollments
  │
  └─< Enrollment  [Student × Teacher Environment × Academic Year]   ← keystone
        • references exactly one Student (mandatory)
        • holds exactly one Grade for the year (immutable within the Enrollment)
        • owns parent contact (teacher-scoped, not global)
        │
        ├─< Group membership     (0..*, all Groups within the Enrollment's Grade)
        ├─< Attendance           [Enrollment × Session Instance]   binary, correctable
        ├─< Recitation           [Enrollment × Session Instance]   Studied / Not-Studied
        ├─  Payment              [Enrollment × Calendar Month]     status + amount
        ├─  State                [Enrollment × Calendar Month]     {Good | Needs Follow-up | At Risk}
        ├─  Rating               [Enrollment × Calendar Month]     teacher 1–5
        └─  Teacher Private Notes                                  teacher-only

Teacher Environment  (the tenant boundary) owns:
  • Academic Years   (teacher-scoped, own lifecycle)
  • Grades           (own the monthly fee)
  • Groups           (belong to a Grade)
  • Schedules        (Group recurring slot)
  • Session Instances(belong to a Group; first-class lifecycle)
  • Video metadata   (+ targeting + external reference)
```

See [`diagrams/domain/ownership-tree.mmd`](../diagrams/domain/ownership-tree.mmd).

## Key relationships

- A **Teacher Environment** contains many Academic Years; each Academic Year frames many Enrollments.
- A **Student** may hold many Enrollments (across teachers and across years), but **at most one** per
  `(Teacher Environment × Academic Year)`.
- An **Enrollment** has exactly one Grade and zero-or-more Group memberships, all Groups within that
  Grade.
- A **Session Instance** belongs to one Group; attendance and recitation records reference it.
- **Payment, State, Rating** are monthly records scoped to the Enrollment; their academic (Grade)
  context is derived from the Enrollment, which is constant.

## Ownership of student data (the split)

| Data | Owner | Notes |
|------|-------|-------|
| Name, phone/login | **Student** (global) | Shared identity across teachers |
| Parent contact | **Enrollment** (teacher-scoped) | Not global; each teacher records their own |
| Grade, Group memberships | **Enrollment** | Grade constant per Enrollment |
| Attendance, Recitation | **Enrollment** (via Session Instance) | Group-level |
| Payment, State, Rating | **Enrollment** | Monthly |
| Teacher Private Notes | **Enrollment** | Teacher-only |

> **Provenance:** The original brief implied the teacher registers all student data and implied a
> single teacher scope. Two refinements were made deliberately: (1) student **identity** is global
> so one real student can use Madar with multiple teachers; (2) **parent contact** is
> Enrollment-owned (teacher-scoped), not global — avoiding a shared global Parent entity.

## Conceptual sub-domains

These are the natural boundaries of Madar's world. They are **conceptual** — they inform the
module structure in `04-architecture/` but do **not** imply microservices.

1. **Identity & Enrollment** — Student, Enrollment, Grade, Group
2. **Educational Operations** — Schedule, Session Instance, Attendance, Recitation
3. **Financials** — Grade fee, Payment
4. **Student Evaluation** — State, Rating, Teacher Private Notes
5. **Content** — Video and targeting
6. **Learning & AI** — AI Assistant, AI Quiz
7. **Notifications** — notification events and dispatch

## Cross-boundary flows (detailed in `05-runtime/`)

- **State pipeline:** Educational Operations evidence → (optional) AI recommendation → Teacher
  finalizes → stored in Student Evaluation.
- **Auto-notification:** Absent / Not-Studied outcomes (Educational Operations) → Notifications.

## Negative space (deliberately not in the domain)

Center / Room / Location, Parent (as an entity), and Assistant/Secretary roles are **not** domain
concepts in V1. See the glossary's "Terms deliberately absent."
