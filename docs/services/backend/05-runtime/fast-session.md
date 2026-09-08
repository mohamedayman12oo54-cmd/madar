# Backend Runtime — Fast Session

> **Authority:** Descriptive (canonical for the Backend runtime of Fast Session).
> **Specializes:** `../../../05-runtime/fast-session.md`,
> `../../../10-decisions/ADR-005-async-notification-dispatch.md`.
> **Diagram:** `../diagrams/runtime/fast-session-sequence.mmd`.

The Fast Session is the teacher's live interface for recording attendance and recitation one student
at a time. This document specializes the system's Fast-Session runtime into Backend execution terms.
The system narrative and validated semantics are authoritative upstream and are not re-narrated here.

## The minimal per-tap synchronous path

Each Present/Absent (attendance) or Studied/Not-Studied (recitation) action is handled as an
**independent, individually-committed write** (`../02-requirements/backend-requirements.md`, BR-2).
The synchronous server-side work is limited to:

1. authenticate/authorize and establish the applicable context;
2. validate the requested state transition / business rules (including Session-Instance-is-Open and
   the applicable invariants — BR-1);
3. persist the domain record/change;
4. where a notification is required (**Absent**, **Not-Studied**): persist the corresponding
   **durable event hand-off atomically** with the domain change, within the emitting module's
   transactional boundary (`../03-internal-boundaries/module-boundaries.md`, BND-3);
5. return the result; the UI advances immediately.

The synchronous path performs **no** notification delivery, **no** AI execution, **no** cross-student
batch, and **no** unrelated async work. **Skip** advances past the student with no record and no
event.

## Flow

```
Teacher opens group session → Session Instance: Planned → Open
  loop per student:
    tap Present/Absent  (or Studied/Not-Studied/Skip)
      → authn/authz + context
      → validate transition / invariants
      → persist record                         (tenant-scoped write)
      → IF Absent or Not-Studied:
           record + durable notification event hand-off committed in one transaction
             (within the emitting module's transactional boundary)
      → return; UI advances                     (no wait on delivery)
    (Skip: advance, no record, no event)
Teacher closes session → Session Instance: Closed
        │
        ▼   [Worker]
  notification dispatch runs asynchronously; may fail independently
    (internal worker job; not a client-facing operation)

Correction (later):
  Closed → Reopened → flip mark → re-persist → Closed
  prior fired notifications stand; a new Absent/Not-Studied may fire a new event hand-off
```

## Commit and correction semantics

- **Per-tap persistence, not batch-on-close.** Records persist per tap while the Session Instance is
  Open; closing the session is a lifecycle transition
  (`../../../03-domain/lifecycles.md`), not a flush of pending writes. This avoids losing a session's
  work if the client is interrupted before close.
- **Atomic record + event; async delivery.** The triggering record and its notification event
  hand-off are committed transactionally (no "record saved, event lost" window); **delivery** then
  happens asynchronously on the Worker and may fail independently without affecting the record
  (`../../../10-decisions/ADR-005-async-notification-dispatch.md`).
- **Fired notifications are not retracted.** A correction does not undo an already-dispatched
  notification; a later new Absent/Not-Studied may produce a **new** event hand-off. Notifications are
  a record of what happened, not a live mirror of current state.

## Why this shape

The minimal per-tap synchronous path keeps the live interaction fast at 40–50 students per group (the
qualitative bar in `../../../02-requirements/quality.md`) while committing the notification event in the
same transaction as the record guarantees no lost events. Pushing delivery to the Worker keeps the
latency-sensitive path clean, consistent with the Web/Worker split
(`../04-architecture/execution-model.md`).
