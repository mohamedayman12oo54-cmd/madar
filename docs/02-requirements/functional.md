# Functional Requirements

> **Authority:** Normative (system-shall statements & rules).
> **Source of truth** for the behavioral rules of each V1 capability.
> **Depends on:** `01-product/scope.md`, `03-domain/`.
> **Scope note:** these are the validated behavioral rules. Concrete UI, endpoints, and serialized
> schemas are produced later (Contracts detail / implementation) and are not invented here.

## Environment structure

- The system shall let a teacher create Grades within their environment, Groups within a Grade, and
  Schedules for a Group.
- The system shall let a teacher register students and manage student profiles.
- A student shall belong to exactly one Grade per Enrollment (INV-3) and may hold membership in
  multiple Groups within that Grade (INV-4).

## Attendance

- The system shall record attendance as **binary**: Present / Absent. There is no "late" state and no
  absence-reason workflow in V1.
- Attendance shall be scoped to `Enrollment × Session Instance` (INV-8); attendance in one Group's
  session is independent of another Group's session.
- The teacher shall be able to **correct** an attendance record after the session.
- Recording **Absent** shall generate an automatic notification (see `05-runtime/fast-session.md`).

## Recitation / study tracking

- The system shall record recitation outcomes: **Studied** and **Not-Studied** persist; **Skip**
  records nothing (advance only).
- Recording **Not-Studied** shall generate an automatic notification.
- Recitation shall be scoped to `Enrollment × Session Instance`.

## Payments

- The system shall record a payment as `Enrollment × Calendar Month`: paid/unpaid status + the
  applicable monthly amount, with basic history.
- The monthly fee is owned by the **Grade** (INV-5); attending a second Group in the same Grade
  creates no additional obligation.
- Record-only: no online processing, accounting, partial payments, or discount system (V1).

## Student State

- The system shall support a monthly Student State per `Enrollment × Calendar Month` from the
  controlled vocabulary **{Good, Needs Follow-up, At Risk}**.
- The State shall be produced by: system evidence → optional AI recommendation (advisory) → **teacher
  finalizes**. The teacher is the final authority; AI is never authoritative.

## Monthly Rating

- The system shall support a **teacher-assigned 1–5** monthly Rating per `Enrollment × Calendar
  Month`, distinct from State. AI does not own the Rating.

## Notifications

- The V1 notification event set shall be bounded to: **Absent** (auto), **Not-Studied** (auto), **New
  video available**, **Monthly rating published**, and **Teacher manual broadcast** to Groups/Grades.
- Manual teacher broadcast is a committed V1 capability.
- There is no teacher-published quiz and no "new quiz available" notification (the AI Quiz is
  student-initiated).

## Video & content

- The system shall let a teacher upload a video and target it to students/groups/grades; students
  shall access videos targeted to them. Flow: upload → target → watch.

## Student area & visibility

- A student shall see their own: attendance, recitation results, payment **status**, monthly State,
  monthly Rating, targeted videos, notifications, and quiz results.
- **Teacher Private Notes shall never be visible to the student.**

## AI features

- The **AI Study Assistant** shall operate as a general educational tutor grounded in the central
  curated Knowledge Base, with a bounded source contract; it is not scoped to the student's
  records/identity in V1.
- The **AI Quiz** shall be **student-initiated**, generated from teacher-provided content, and
  auto-scored where the question type allows.
- AI operations shall be asynchronous and failure-tolerant; AI failure shall never block or corrupt
  deterministic data (see `05-runtime/` and ADR-006).

## Billing (Teacher ↔ Madar commercial relationship — distinct from Payments above)

> **Do not conflate with the Payments section above.** Payments (above) is the teacher recording a
> **student's** monthly Grade-fee status inside their environment. Billing (here) is the **Teacher's**
> own commercial relationship with Madar. They are unrelated features; see
> `01-product/commercial-model.md` and `00-overview/glossary.md`.

- The system shall support exactly three paid plans with fixed prices, student caps, and feature deltas
  as recorded in `01-product/commercial-model.md` (Plan 1/2/3). No additional tier, annual billing
  option, or discount mechanism is required or implied.
- The system shall grant a Teacher Account a 16-day Free Trial, starting at the Backend-authoritative
  instant of account activation + Environment establishment, with the full Plan 3 feature set and a
  250-student cap, no payment card required, and no auto-conversion to a paid plan.
- The system shall track a Subscription's billing period as exactly 30 elapsed days per cycle (never
  calendar-month arithmetic), support auto-renewal for subscriptions on an appropriate recurring-payment
  agreement, and apply cancellation at the end of the already-paid period only.
- The system shall not immediately terminate access on a single failed renewal attempt; a limited
  retry/notification/grace-period behavior is required, with exact numeric parameters tracked as open
  (`01-product/commercial-model.md` §Open items).
- The system shall never destroy a Teacher Account or its data due to an access-not-granted state, and
  shall preserve the Teacher's ability to authenticate, resolve billing, and review/export their own
  data in that state. Paid-capability gating shall be enforced at the Backend, not only hidden in the
  Frontend.
- Billing persistence and enforcement are owned by a dedicated `billing` Backend module, distinct from
  `financials` — see `06-data/data-model.md` and
  `services/backend/06-data/data-model.md`.

## Homework (fenced)

Homework upload/annotation is outside the V1 Definition-of-Done. Its feasibility go/no-go is a
Requirements-phase gate (`01-product/scope.md`). No committed functional requirement depends on it.
