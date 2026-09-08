# Product Definition

> **Authority:** Descriptive · **Source of truth** for product vision, users, and V1 scope.
> **Depends on:** `00-overview/system-overview.md`.

## Vision

Move a private teacher from managing their educational operation with **notebook + memory +
WhatsApp + scattered tools** to **one organized digital environment**. The target outcome is not
"Madar has many features" but the teacher saying *"I don't know how I did this before Madar."*

## Users

| User | Role | V1 surface |
|------|------|-----------|
| **Teacher** | Primary customer; owns and operates the environment | Responsive web |
| **Student** | Secondary user; consumes their area + selected active features | Mobile-first web |
| **Content Maintainer** | Internal Madar operator; curates the central Knowledge Base | Internal web tool |

## Core value & irreducible core

**Irreducible core:** *managing students and their educational records.* Every other capability
orbits it — attendance, recitation, payments, content, notifications, evaluation, the student area,
and AI are valuable because they maintain an organized educational environment around the teacher's
students.

## V1 capabilities

**Committed (V1-core):**
Teacher environment (grades, groups, schedules) · student registration & profiles · attendance +
fast-attendance session · recitation/study tracking + fast session · payment tracking · video upload
& targeting · notifications · student states + monthly rating · student-facing area · AI (study
assistant + AI quiz).

**Fenced (feasibility-dependent, outside the V1 Definition-of-Done):**
Homework upload/annotation. Its go/no-go is decided at feasibility review; if it fails, V1 is still
complete. See [`scope.md`](scope.md).

## Central V1 experience

```
Teacher manages the environment → manages students & groups → runs real teaching sessions
   → records attendance & educational activity → manages content & information
   → students access their own area and interact with selected capabilities (incl. AI)
```

## Success criteria

Success is **behavioral adoption and delivered value**, not signup volume:

- Teachers use Madar in their real daily workflow.
- Core student/session information lives in Madar rather than notebooks/scattered records.
- Teachers report meaningful time/effort savings.
- Continued use across a full teaching term.

A small number of teachers using Madar deeply is stronger evidence than many weak signups.

## Product-level provenance

Decisions that intentionally refined or superseded the original brief (see
[`../10-decisions/rejected-deferred.md`](../10-decisions/rejected-deferred.md)):

- **AI Study Assistant** redefined as a **general educational tutor** on a central curated KB — not
  scoped to the student's records/identity in V1.
- **Multi-teacher student usage is committed V1** — a student may actively operate under multiple
  teachers, switching between strictly isolated environments.
- **Homework fenced** from the V1 Definition-of-Done.

The full product-decision log, with the brief-supersession provenance for each, is in
[`decisions-log.md`](decisions-log.md).
