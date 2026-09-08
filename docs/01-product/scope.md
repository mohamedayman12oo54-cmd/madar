# Scope

> **Authority:** Normative for the V1 boundary (what is in / deliberately out).
> **Depends on:** `product.md`.

## Capability classification

| Capability | V1 classification |
|------------|-------------------|
| Teacher environment + grades + groups & schedules | V1-core |
| Student registration + profiles | V1-core |
| Attendance + fast-attendance session | V1-core |
| Recitation/study tracking + fast session | V1-core |
| Payment tracking | V1-core |
| Video upload & targeting | V1-core |
| Notifications | V1-core |
| Student states + monthly rating | V1-core |
| Student-facing area | V1-core |
| AI study assistant + AI quiz | V1-core |
| Homework upload/annotation | **Fenced** — feasibility-dependent, outside Definition-of-Done |

Breadth is acceptable because the team has the capacity (including dedicated AI engineering). "V1-core"
does not mean equal depth for every capability — it means committed to the V1 experience.

## Inner boundaries (the ceilings that keep V1 from becoming an LMS)

**Payments** — record-only. *Does:* monthly paid/unpaid status, monthly amount, basic history.
*Does not:* online payment processing, accounting/invoicing, partial payments, discount systems,
per-session pricing. "Madar records payment information; it is not an accounting/payment platform."

**Notifications** — *channels:* in-app + push only. *Out:* SMS, WhatsApp, email. It delivers relevant
educational/product events, not a general communication platform.

**Video** — *flow:* upload → target → watch. *Out:* manual encoding/quality controls, offline/download,
comments/discussion, consumption analytics.

**Student Area** — a real surface: viewer/consumer + selected active participation (AI quiz, AI
assistant, videos, records/status, notifications). *Not* a full online-learning platform; no social,
communication, or course-management ecosystem.

**AI** — first-class V1, each feature with a bounded source/input contract:
- **Study Assistant** ← central curated Knowledge Base (works out of the box; teachers do not curate
  AI sources in V1).
- **AI Quiz** ← teacher-provided content (e.g., uploaded video); **student-initiated**.
- **State recommendation** ← relevant student evidence in → advisory recommendation → stored State.

## Non-goals (V1)

Madar is **not**: an online-learning platform / LMS, a replacement for offline teaching, a large exam
platform, an accounting/payment system, or a general communication platform. AI is not the core and is
not used merely because a feature *could* use AI.

## The Homework fence

Homework upload/annotation is **explicitly outside the V1 Definition-of-Done**. It may be implemented
during V1 **only if** feasibility validation passes without unacceptable risk to committed scope,
quality, or timeline. The go/no-go is decided at the Requirements/feasibility phase. If the gate
fails, **V1 is still complete without Homework.** This prevents "feasibility-dependent" from becoming
an uncontrolled scope dependency.
