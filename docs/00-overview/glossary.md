# Glossary

> **Authority:** Normative for terminology. Each term has exactly one canonical definition here;
> all other documents use these terms with this meaning.

| Term | Definition |
|------|------------|
| **Teacher Environment** | The isolated space belonging to one teacher. The universal tenant boundary: every teacher-scoped record carries its `teacher_environment_id`. Owns Academic Years, Grades, Groups, Schedules, video metadata, and (through Enrollments) all educational records. |
| **Student** | The **global** identity/account of a real student (name, phone/login, claim state). Exists independently of any teacher. The **only** entity that is not teacher-scoped. May be unclaimed until the student completes phone-based claiming. |
| **Enrollment** | The **keystone** teacher-scoped relationship: `Student × Teacher Environment × Academic Year`. Owns the student's Grade for that year, their Group memberships, and all teacher-scoped educational records (attendance, recitation, payment, state, rating, notes, parent contact). At most one Enrollment per (Student × Teacher Environment × Academic Year). |
| **Academic Year** | A **teacher-scoped** period within a Teacher Environment, with its own boundaries and lifecycle. Madar does not assume one platform-wide academic calendar. A new year creates new Enrollments; nothing is auto-carried-forward as a domain rule. |
| **Grade** | The academic + **financial** unit (e.g., "Second Preparatory"). Owns the **monthly fee**. A student belongs to exactly one Grade per Enrollment; the Grade is immutable within an Enrollment. |
| **Group** | The **teaching/session organization** unit within a Grade (e.g., "Group A, Monday 6:00 PM"). A student may attend multiple Groups, but all within their Enrollment's Grade. A Group owns no fee. |
| **Schedule** | The recurring expected teaching arrangement for a Group (e.g., "Group A → Monday 6:00 PM"). |
| **Session Instance** | A **first-class** actual occurrence of a teaching session for a Group on a date/slot. Lifecycle: `Planned → Open → Closed`, with `Closed → Reopened → Closed` for correction. Attendance and recitation records attach to a Session Instance. May be scheduled or ad-hoc (make-up). |
| **Attendance** | A per-`Enrollment × Session Instance` record; binary **Present / Absent**; correctable. No "late" state and no absence-reason in V1. Recording **Absent** triggers an automatic notification. |
| **Recitation (Study tracking)** | A per-`Enrollment × Session Instance` record of study readiness. **Studied** and **Not-Studied** persist; **Skip** records nothing (advance only). Recording **Not-Studied** triggers an automatic notification. |
| **Payment** | A per-`Enrollment × Calendar Month` record of the student's monthly fee status (paid/unpaid) and amount. Record-only: no online processing, accounting, partial payments, or discounts in V1. The fee is owned by the **Grade**. |
| **State (Student State)** | A per-`Enrollment × Calendar Month` structured status from a controlled vocabulary: **Good · Needs Follow-up · At Risk**. Produced by: system evidence → optional AI recommendation (advisory) → **teacher finalizes**. The teacher is the final authority. |
| **Rating (Monthly Rating)** | A per-`Enrollment × Calendar Month` **teacher-assigned 1–5** evaluation. Distinct from State. AI does not own it. |
| **Teacher Private Notes** | Teacher-authored notes about a student. **Teacher-only**; never visible to the student. |
| **Notification** | A fired **event** describing something that happened (Absent, Not-Studied, new video, monthly rating published, teacher manual broadcast). Fired-and-forgotten: correcting a record later does **not** retract a sent notification. V1 channels: in-app + push only. |
| **Video** | Teacher-uploaded content, targeted to students/groups/grades. Madar stores **metadata + targeting + an external reference**; the binary lives in external storage. Flow: upload → target → watch. |
| **AI Study Assistant** | A **general educational tutor** grounded in the central curated Knowledge Base, with a bounded source/input contract. **Not** scoped to the individual student's records or identity in V1. |
| **AI Quiz** | A **student-initiated** quiz generated from **teacher-provided content** (e.g., a watched video). Auto-scored where the question type allows. No teacher-published quiz capability exists in V1. |
| **Knowledge Base (KB)** | The central, product-owned, curated educational content the AI Study Assistant uses. Internal to Madar, in its own store (not ordinary transactional data). Lifecycle: draft → published/versioned; only published content is authoritative. |
| **Content Maintainer** | The internal Madar operator who curates the Knowledge Base. Has no access to teacher educational records. |
| **Claiming** | The phone-based process by which an unclaimed, teacher-created Student identity becomes an authenticating account. Establishes access to the **existing** identity; does not create a new one or rebuild records. |

## Lifecycle terms (Teacher entry & access)

| Term | Definition |
|------|------------|
| **Product entry point** | The point at which a prospective Teacher reaches Madar and can begin the journey (typically via the Free Trial). Acquisition channels and UI are out of scope. See `03-domain/actor-lifecycles.md`. |
| **Teacher Account** | A Madar user/account held by a Teacher as a distinct actor. Created via the Teacher's own account-creation path (distinct from student claiming; Students are teacher-created and do not self-signup). Authentication mechanics are deferred. |
| **Free Trial** | The initial access state in which a Teacher can use Madar as their own educational environment before subscribing. Existence and purpose are defined; exact duration and mechanics are deferred. See `01-product/access-lifecycle.md`. |
| **Subscription** | The access state that grants a Teacher continued use of Madar after the Free Trial ends. Commercial mechanics (pricing, billing, provider) are deferred. Distinct from student fee tracking. |
| **Access state** | The Teacher's current trial/subscription status that governs whether they currently have access to their environment and its capabilities. |

> **Environment establishment note:** the **Teacher Environment** (defined above as the tenant
> boundary) is *established as part of the Teacher's product journey* — it is not a pre-existing
> given. Its origin lifecycle is documented in `03-domain/actor-lifecycles.md`; its
> isolation/tenant-boundary meaning is unchanged.

## Terms deliberately absent in V1

These are **not** domain concepts in V1 (recorded so they are not accidentally introduced later):
**Center / Room / physical Location** (context only, not modeled), **Parent** (data, not an entity
or actor), **Assistant / Secretary / Center-Admin** (no such role).
