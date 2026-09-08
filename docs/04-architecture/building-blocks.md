# Building Blocks

> **Authority:** Descriptive.
> **Depends on:** `architecture.md`, `03-domain/`.
> **Diagram:** [`diagrams/architecture/building-blocks.mmd`](../diagrams/architecture/building-blocks.mmd).

## Layered view

```
        Clients (web):  Teacher (responsive) · Student (mobile-first) · Content Maintainer (internal)
                                        │
                                        ▼   one unified REST API (/api/v1)
                        ┌───────────────────────────────────┐
                        │  Request boundary                  │
                        │  Auth + Tenant Context (ADR-008)   │  ← establishes actor + environment,
                        └───────────────────────────────────┘     server-derived (layer 1 of ADR-004)
                                        │
   ┌────────────────────────────────────────────────────────────────────────────┐
   │                     MODULAR MONOLITH (one deployable)                        │
   │                                                                             │
   │   Identity &      Educational       Financials      Student                 │
   │   Enrollment      Operations                        Evaluation              │
   │                                                                             │
   │   Content         Learning & AI ───► (LLM seam)     Notifications           │
   │                                                                             │
   │   Data-access boundary: tenant scope enforced (layer 2 of ADR-004/007)       │
   └────────────────────────────────────────────────────────────────────────────┘
                                        │
                        ┌───────────────┼───────────────┐
                        ▼               ▼               ▼
                  Persistence     Push delivery    Video storage/
                  (+ KB store)     (external)       streaming (external)
                  logical tenant
                  isolation
```

## Module responsibilities & dependencies

| Module | Owns | Depends on | Notes |
|--------|------|-----------|-------|
| **Identity & Enrollment** | Student, Enrollment, Grade, Group, Academic Year | — | Foundation; other modules reference Enrollment |
| **Educational Operations** | Schedule, Session Instance, Attendance, Recitation | Identity & Enrollment | Emits Absent / Not-Studied events |
| **Financials** | Grade fee, Payment | Identity & Enrollment | Fee owned by Grade (INV-5) |
| **Student Evaluation** | State, Rating, Notes | Identity & Enrollment; Learning & AI (advisory) | Teacher finalizes State |
| **Content** | Video metadata + targeting | Identity & Enrollment; Video interface | Blob external |
| **Learning & AI** | AI orchestration | LLM interface; KB (Assistant); Content (Quiz); evidence (State rec) | Only module crossing the LLM seam |
| **Notifications** | Notification events + dispatch | Consumes events from other modules; Push interface | Async consumer |

## Cross-module collaboration

- **Notifications** is a cross-module **async consumer**. Educational Operations emits Absent /
  Not-Studied events; other modules emit new-video, rating-published, and manual-broadcast events.
  The triggering record and the notification event are committed transactionally; delivery is async
  (ADR-005). Notification events are fired-and-forgotten.
- **Learning & AI** is the only module with an external functional dependency (the LLM). It exposes
  a clean internal interface so no other module depends on provider details (ADR-002).
- **Student Evaluation** consults Learning & AI for an **advisory** State recommendation; the teacher
  remains the final authority (ADR-006).

## Enforcement layers (recap)

1. **Request boundary** — authenticates the actor, resolves them against authorized environments, and
   establishes the active `teacher_environment_id` context. The client cannot supply an arbitrary
   tenant (ADR-008).
2. **Data-access boundary** — every teacher-scoped access is constrained by the established tenant
   context. Modules cannot bypass this on the normal path (ADR-004/007).

Two layers, so a single missed check does not leak data across tenants. This is the structural
guarantee behind INV-7.
