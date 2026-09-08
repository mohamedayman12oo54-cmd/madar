# Runtime — Student State Pipeline

> **Authority:** Descriptive (canonical for State-recommendation runtime behavior).
> **Depends on:** `03-domain/domain-model.md`, `02-requirements/functional.md`, ADR-006.
> **Diagram:** [`../diagrams/runtime/state-pipeline.mmd`](../diagrams/runtime/state-pipeline.mmd).

The Student State pipeline turns recorded evidence into a monthly State
(`Enrollment × Calendar Month`, vocabulary {Good, Needs Follow-up, At Risk}). It is a multi-module,
externally-dependent flow, and the teacher is always the final authority.

## Validated semantics

- **On-demand, not batch.** The recommendation is generated when the teacher requests/reviews the
  student's State for the month — not precomputed for every student at month-end.
- **Evidence → AI recommendation → teacher-final.** The system gathers relevant evidence (attendance,
  recitation, quiz performance — tenant/enrollment-scoped); Learning & AI requests an **advisory**
  recommendation.
- **Asynchronous.** The recommendation request is asynchronous; the teacher's request is not
  synchronously blocked on the external LLM.
- **AI is never authoritative.** The teacher may accept, modify, or assign the State directly. The
  stored State is the teacher's decision.
- **Failure-tolerant.** If the LLM fails/times out, no recommendation is available and the teacher
  proceeds with manual finalization. Deterministic records and the teacher's authority are
  independent of AI availability (ADR-006).
- **Persistence.** The advisory recommendation and the finalized State are persisted; the LLM
  interaction is never the source of truth.

## Flow

```
Teacher opens student's month
  → Madar gathers evidence (tenant/enrollment-scoped)
  → [async] Learning & AI → LLM interface → suggested State
       ├─ success: advisory recommendation shown
       └─ fail/timeout: no recommendation; teacher proceeds manually
Teacher finalizes State {Good | Needs Follow-up | At Risk}   ← authoritative, persisted
```
