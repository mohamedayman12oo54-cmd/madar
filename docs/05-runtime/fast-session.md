# Runtime — Fast Session

> **Authority:** Descriptive (canonical for Fast Session runtime semantics).
> **Source of truth** for how Fast Attendance / Fast Recitation behave at runtime, including the
> commit model and notification timing.
> **Depends on:** `03-domain/lifecycles.md` (Session Instance states), ADR-005, ADR-006.
> **Diagram:** [`../diagrams/runtime/fast-session.mmd`](../diagrams/runtime/fast-session.mmd).

The Fast Session is the teacher's live, in-session interface for recording attendance and recitation
one student at a time. It is the sharpest expression of the #2 quality attribute (fast-session
responsiveness), so its runtime semantics are validated explicitly.

## Validated semantics

- **Per-tap persistence.** Each Present/Absent (attendance) or Studied/Not-Studied (recitation) action
  is persisted **as the teacher performs it** — durable progress per tap.
- **UI advances immediately.** After a mark is recorded, the interface moves to the next student
  without waiting on any downstream work (notifications, AI, etc.).
- **Session Close is a lifecycle transition, not the batch-commit point.** Records are already
  persisted per-tap while the Session Instance is **Open**; closing the session moves it `Open →
  Closed` (see `03-domain/lifecycles.md`) but does **not** flush a batch of pending writes. This
  avoids losing a whole session's work if the client is interrupted before close.
- **Notification events are asynchronous after commit.** For **Absent** and **Not-Studied**, the
  triggering record and its notification **event** are committed **transactionally** (no "record
  saved, event lost" window); **delivery** then happens **asynchronously** via the worker process and
  may fail independently without affecting the record (ADR-005).
- **Skip records nothing.** Choosing Skip advances past the student without creating a recitation
  result — no record, no event.

## Correction semantics

- **Corrections persist.** A record may be corrected after the session; corrections are persisted.
  Correcting a Closed session uses the `Closed → Reopened → Closed` path (a correction of the same
  occurrence, not a new session — `03-domain/lifecycles.md`).
- **Fired notifications are not retracted.** A notification already dispatched describes an event that
  occurred; a later correction does **not** undo it. Notifications are a record of what happened, not
  a live mirror of current state.
- **A later new Absent/Not-Studied may produce a new notification event.** If a correction changes a
  record back to Absent (or Not-Studied), that new outcome may generate a **new** notification event.

## Flow

```
Teacher opens group session → Session Instance: Planned → Open
  loop per student:
    tap Present/Absent  (or Studied/Not-Studied/Skip)
      → record persists immediately        (tenant-scoped write)
      → IF Absent or Not-Studied:
           record + notification EVENT committed in one transaction
      → UI advances to next student         (no wait on delivery)
    (Skip: advance, no record, no event)
Teacher closes session → Session Instance: Closed
  [worker] notification delivery runs asynchronously; may fail independently

Correction (later):
  Closed → Reopened → flip mark → re-persist → Closed
  prior notification stands; a new Absent/Not-Studied may fire a new event
```

## Why this shape

Per-tap persistence + immediate UI advance keeps the live interaction fast at 40–50 students per
group (the quality bar in `02-requirements/quality.md`). Committing the notification **event** in the
same transaction as the record guarantees no lost events, while pushing **delivery** to the worker
keeps the latency-sensitive path clean (ADR-005, ADR-012).
