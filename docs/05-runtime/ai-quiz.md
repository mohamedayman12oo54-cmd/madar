# Runtime — AI Quiz

> **Authority:** Descriptive (canonical for AI Quiz runtime behavior).
> **Depends on:** `02-requirements/functional.md`, `07-contracts/api-contract.md`, ADR-006, ADR-011.
> **Diagram:** [`../diagrams/runtime/ai-quiz.mmd`](../diagrams/runtime/ai-quiz.mmd).

The AI Quiz is **student-initiated**: after watching targeted content, a student requests a quiz
generated from that teacher-provided content. There is no teacher-published quiz in V1.

## Validated semantics

- **Student-initiated.** The student requests the quiz; the source is the teacher-provided content
  (e.g., the watched video).
- **Asynchronous, submit → operation-id → poll.** Submission returns an operation identifier; the
  client polls status/result (`Submitted → Processing → Succeeded | Failed`). No streaming in V1.
- **Idempotent submission.** A retried submission does not create a duplicate operation (ADR-011).
- **Failure-tolerant, no partial quiz.** On failure/timeout the student receives a clear failure state
  and a retry path; **no** incomplete/invalid quiz is persisted or presented as successful.
- **Persistence.** A generated quiz is persisted before the student answers; answers and scoring
  results are persisted as educational records (student-visible). The LLM is never the source of truth.
- **Auto-scoring** applies where the question type allows.

## Flow

```
Student finishes targeted video → requests quiz
  → [async] Learning & AI (source = teacher content) → LLM interface → quiz
       ├─ success: quiz persisted → student answers → auto-scored → result persisted (student-visible)
       └─ fail/timeout: clear failure state + retry; NO partial/invalid quiz persisted
```
