# Domain Invariants

> **Authority:** **Normative.** These rules MUST hold. Implementation, data design, and contracts
> are all constrained by them. If code or schema can violate one of these on a normal path, the
> design is wrong.
> **Source of truth** for the rules below.
> **Depends on:** `domain-model.md`.

## The invariants

### INV-1 — Enrollment references exactly one Student
Every Enrollment references exactly one global Student. An Enrollment cannot exist without a Student.
(A Student, however, may exist with zero Enrollments — e.g., before a teacher enrolls them, or after
their only relationship ends.)

### INV-2 — One Enrollment per (Student × Teacher Environment × Academic Year)
A student has **at most one** Enrollment with a given teacher for a given Academic Year. Continuing
with the same teacher next year means a **new** Enrollment, not an extension of the old one.

### INV-3 — One Grade per Enrollment; Grade is immutable within it
A student belongs to **exactly one Grade** within a Teacher Environment at a time, carried by the
Enrollment. The Grade **does not change within an Enrollment**. A grade change happens only across
Academic Years, through a new Enrollment. A student cannot simultaneously belong to two Grades under
the same teacher.

### INV-4 — Group membership stays within the Enrollment's Grade
A student may attend multiple Groups, but **every** Group they attend must belong to their
Enrollment's Grade. (Real case: a Second-Preparatory student normally in Group A may attend Group B
or C when their schedule requires — all within Second Preparatory.)

### INV-5 — Grade owns the fee; Payment is monthly per Enrollment
The monthly fee is owned by the **Grade**, not the Group. Groups within the same Grade share the
same fee. A Payment is scoped to `Enrollment × Calendar Month`; attending a second Group in the same
Grade creates **no** additional payment obligation.

> **Provenance:** The original brief implied the *Group* had the fee/schedule. This was corrected:
> the **Grade** owns the fee. This resolves what would otherwise be a contradiction — a student
> attending two Groups in one Grade must not owe two fees.

### INV-6 — Historical academic context is preserved
Monthly records (Payment, State, Rating) retain the academic (Grade) context in effect when they
were created. Because Grade is immutable within an Enrollment (INV-3), this context is **derived
from the Enrollment** and never rewritten. A later year's Enrollment/Grade must never reinterpret a
prior year's records.

### INV-7 — Multi-teacher isolation
For the same global Student, Teacher B must never gain access to Teacher A's Enrollment records.
Isolation applies at the **relationship-and-records** level (the Teacher Environment), **not** at the
student-identity level — the identity may be global; the records are not.

> **Provenance:** The brief stated data is "isolated between teachers." This was refined: the
> **student identity** may be global (so one real student uses Madar with several teachers), while
> the **records** remain strictly teacher-scoped. Isolation is a boundary on records, not identity.

### INV-8 — Session Instance owns operational records
Attendance and Recitation records exist only in the context of a **Session Instance**. If a student
belongs to multiple Groups, their attendance/recitation in one Group's session is independent of
another Group's session (`Enrollment × Session Instance`).

## Enforcement note

INV-7 is enforced structurally, not by convention — see the tenant-isolation decisions
[ADR-004](../10-decisions/ADR-004-two-layer-tenant-isolation.md),
[ADR-007](../10-decisions/ADR-007-two-level-data-scoping.md), and
[ADR-008](../10-decisions/ADR-008-server-derived-tenant-context.md). The other invariants are
domain rules the data model and application logic must uphold; their mechanisms are covered in
`06-data/` (planned) and `07-contracts/`.
