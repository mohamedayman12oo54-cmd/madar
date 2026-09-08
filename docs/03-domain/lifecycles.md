# Domain Lifecycles

> **Authority:** Descriptive (the state models are canonical).
> **Source of truth** for the Session Instance and Enrollment/Academic-Year lifecycles.
> **Depends on:** `domain-model.md`, `invariants.md`.

## Session Instance lifecycle

A Session Instance is a first-class entity representing an actual teaching occurrence for a Group.

```
Planned ──► Open ──► Closed ──► Reopened ──► Closed
                                   ▲______________│
```

| State | Meaning | Records |
|-------|---------|---------|
| **Planned** | An expected upcoming session | none yet |
| **Open** | The active teaching context | attendance & recitation can be captured |
| **Closed** | A completed session | records exist; session is done |
| **Reopened** | An intentional correction of a Closed session | records may be edited |

Rules:
- Attendance and recitation are captured while the session is **Open**.
- **Reopening** is an explicit correction mechanism. It does **not** create a new occurrence — the
  same Session Instance re-opens, is corrected, and closes again.
- A Session Instance may originate from a Group's **Schedule** (scheduled) or be created **ad-hoc**
  (a make-up class outside the normal schedule). The schedule never prevents recording a real
  session that happened off-schedule.

See [`diagrams/domain/session-lifecycle.mmd`](../diagrams/domain/session-lifecycle.mmd).

### Correction and notifications

When a Closed session is reopened and a mark is corrected, previously **fired notifications are not
retracted** (they are events describing what happened, not a live mirror of current state). A
correction that produces a new Absent/Not-Studied may fire a **new** notification. This is a runtime
rule — see `05-runtime/` (planned) and
[ADR-005](../10-decisions/ADR-005-async-notification-dispatch.md).

## Enrollment / Academic Year lifecycle

Enrollment is scoped to a single Academic Year within a Teacher Environment. Academic Year is
**teacher-scoped** — each teacher defines their own year boundaries; there is no platform-wide
academic calendar.

```
Academic Year starts (teacher-defined)
        │
        ▼
Enrollment created  [Student × Teacher Environment × Academic Year]
        │  • one Grade (fixed for the year)
        │  • Group memberships within that Grade
        │  • accumulates monthly records (Payment, State, Rating) + session records
        ▼
Academic Year ends
        │
        ├─ student continues with this teacher ──► NEW Enrollment for the new year
        ├─ student changes grade ───────────────► NEW Enrollment (new Grade) for the new year
        └─ student leaves this teacher ─────────► no new Enrollment with this teacher
                                                  (the global Student may enroll with another teacher)
```

Rules:
- An Enrollment **ends with the Academic Year**. It is not an indefinite lifetime relationship.
- A new Academic Year creates a **new** Enrollment for continuing students. Prior-year Enrollments
  and their records are retained as historical, read-only context (INV-6).
- A new year does **not** automatically carry forward Groups, Schedules, or rosters as a domain rule.
  Any "clone last year's setup" convenience is a product/UX capability, not part of the domain model.
- Because Grade is fixed per Enrollment (INV-3), a grade change is expressed as a new Enrollment in a
  new year — never as a mutation of the current one.

### Why yearly, not indefinite

This mirrors the real tutoring workflow: from one year to the next, students continue, leave, move up
a grade, or switch teachers. Modeling the relationship per Academic Year gives the domain a clean
yearly boundary while the global Student identity persists across years and teachers.
