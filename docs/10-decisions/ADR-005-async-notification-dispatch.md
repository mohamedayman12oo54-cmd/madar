# ADR-005 — Asynchronous Notification Dispatch

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
During a Fast Session the teacher marks ~40–50 students rapidly; Absent and Not-Studied each trigger a notification. Fast-session responsiveness is the #2 quality attribute. Sending notifications synchronously per tap would risk that responsiveness.

## Decision
**Decouple** notification delivery from the fast-session write path. Each mark persists per tap and the UI advances immediately. The triggering domain record and the notification **event** are committed **transactionally** (no 'record saved, event lost' window); **delivery** then happens **asynchronously** via the worker process. Delivery may fail independently without affecting the record.

## Alternatives considered
- **Synchronous per-tap delivery** — rejected: couples the latency-sensitive path to notification/delivery latency, harming the #2 driver.
- **Batch-commit on session close** — rejected: risks losing a whole session's work if the client is interrupted before close.

## Consequences
- Fast Session stays immediate; notification failures are isolated from record commit.
- Notifications module becomes an asynchronous event consumer.
- Notification semantics are fired-and-forgotten (see the runtime rule): a later record correction does not retract a sent notification.
