# ADR-007 — Two-Level Data Scoping: Teacher-Environment as Tenant Key, Enrollment as Ownership Key

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
ADR-004 needs one mandatory scope key the data-access isolation layer can filter on. But not all teacher-scoped entities belong to an Enrollment — Academic Year, Grade, Group, Schedule, and video metadata exist at the Teacher-Environment level, independent of any single student relationship.

## Decision
Use **two levels**: `teacher_environment_id` is the **universal tenant/isolation key** that every teacher-scoped record carries and the data-access layer filters on. **Enrollment** is the **ownership/relationship key** for enrollment-scoped educational records (attendance, recitation, payment, state, rating, notes). These are intentionally different concepts and must not be conflated.

## Alternatives considered
- **Enrollment as the universal tenant key** — rejected: many teacher-scoped entities have no Enrollment, so it cannot be the universal isolation filter.
- **A single flat key with ad-hoc ownership checks** — rejected: loses the clean, uniform isolation filter.

## Consequences
- The isolation layer is uniform across all teacher-scoped tables (one filter column).
- Enrollment-level ownership is handled above the isolation layer where records are enrollment-scoped.
- Monthly records derive their Grade context from the Enrollment (no duplicated grade key), safe because Grade is immutable within an Enrollment (INV-3).
