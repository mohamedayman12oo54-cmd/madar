# Implementation Plan — Madar Backend V1 (Control Document)

> **Authority:** Layer 4 (derived from System Docs → Backend Service Docs → ADRs).
> **Status:** Assembled (Stage 13). Not READY until Stage 14 validation passes.
> **Scope note:** This control document orients the reader. Canonical detail lives in the sibling
> artifacts; this file does not restate them as independent copies.

## 1. Definition

The Madar Backend Implementation Plan is a **traceable execution model derived from the approved
Documentation baseline**, defining the bounded work, dependencies, execution strategy, verification
path, and operational guidance required to transform documented system intent into verified
implementation outcomes. It is derived, not authored; it never becomes a second source of system truth.

## 2. What is being built (one paragraph)

The Backend is the **server-side application boundary of the Madar modular monolith** (one deployable,
two runtime roles: web + worker; ADR-001/012), realizing **eight** internal modules (Identity &
Enrollment, Educational Operations, Financials, Student Evaluation, Content, Learning & AI,
Notifications, and **Billing** — added after the commercial-design pass, ADR-014) behind a
single versioned REST API (`/api/v1`, ADR-003), with **non-bypassable tenant isolation** on
`teacher_environment_id` (ADR-004/007/008), **composite authorization** (ADR-010), **all-paths invariant
enforcement** (INV-1..9), an **async operation spine** and **transactional event hand-off** (ADR-005/006/011/017),
and **Madar-owned interfaces** to four external dependencies (LLM, Push, Video, Payment; ADR-009/015). The corrected
upstream lifecycle (Teacher account/auth → Environment establishment → Teacher→Student introduction →
Free-Trial/Subscription access state) is represented as **boundary responsibilities with fenced mechanisms**.

## 3. Planning scope (D1)

Full documented Backend V1 scope. No MVP reduction. All documented exclusions/fences remain excluded/fenced
unless promoted through the appropriate decision path. Coverage of the full V1 scope does **not** mean
simultaneous implementation — dependency-aware phasing is expressed in `execution-sequence.md`.

**Negative space (built = never):** Homework (fenced); no product-wide caching, audit logging, rate
limiting, circuit-breakers, or distributed tracing; no inbound integrations **other than the one
ADR-016-approved Kashier payment-result webhook**; no SMS / WhatsApp / email; no teacher-published
quiz; no cross-environment data merge; video blob external; LLM state not persisted. Online payment is
now in scope via the Billing module (`10-decisions/ADR-014-billing-bounded-module.md`) — it is no
longer negative space, but this Implementation Plan document is not itself updated into a Billing
implementation plan by this note.

## 4. Resolved technology decisions (D2)

| # | Decision | Status |
|---|----------|--------|
| D2-1 | **Python + Django**, one deployable / two roles (web + worker), shared codebase/domain/persistence | RESOLVED |
| D2-2 | **Managed relational (Postgres-class)**, single logical datastore, centralized non-bypassable isolation at the data-access boundary, atomic multi-write | RESOLVED (+ narrow spike FND-03) |
| D2-3 | **DB-backed job/queue + transactional Outbox**, worker reconstructs trusted context from persisted server-state, at-least-once, idempotent consumers | RESOLVED (+ narrow spike FND-08) |
| D2-4 | **No separate Backend stack decision** — KB authoring consumes D2-2; AI retrieval/RAG store fenced behind the AI seam | RESOLVED-BY-BOUNDARY |

Full detail and the fenced Nodes are in `decisions.md`.

## 5. Canonical model

- **49 Work Units** = **36 READY · 11 SEAM-READY · 2 SPIKE · 0 BLOCKED**; **9 Nodes**. (`work-breakdown.md`)
- **State semantics** as defined in the package README. BLOCKED is reserved for a WU whose *boundary* cannot
  be established — not for a fenced mechanism/vendor.

## 6. Execution strategy & gates (summary)

**Foundation-first + Risk overlay.** Rationale: the typed graph shows the platform floor + enforcement
substrate as a repeated precondition, and the highest engineering risks (isolation enforcement, Outbox
atomicity) are pulled forward as SPIKEs. Waves: **W0 Investigate → W1 Platform Floor → W2 Enforcement
Substrate → W2.5 Lifecycle Seams (∥) → W3 Identity Core → W4 Educational+Financials → W5 Async &
Cross-Module → W6 AI/Eval/Notify+Fast-Session → W7 API Surface & Ops.** Gate chain: **G-SPIKE → G-FLOOR →
G-GUARD (critical) → G-SEAM → G-IDENTITY → G-EDU → G-ASYNC → G-EXPERIENCE → G-CONTRACT.** Detail in
`execution-sequence.md`.

## 7. Core invariants this plan must preserve

Traceability; justified work; bounded work; executability; verification path per meaningful WU; no silent
contradiction with Documentation; no silent deviation; acyclic blocking graph; **Implemented ≠ Verified**;
Engineering Skills never become project truth. (See `verification.md`, `traceability.md`, `changes.md`.)

## 8. What remains open (fenced) — do not invent

Teacher authentication mechanism; Environment provisioning **trigger** mechanism (cardinality itself is
now **resolved** — ADR-013/INV-9, exactly one Environment per Teacher Account, permanently); secure
Teacher→Student invitation mechanism; the numeric/behavioral sub-decisions of commercial mechanics
(retry/grace numbers, refunds, proration) and the exact access-not-granted behavior; student-claiming
OTP/verification provider; AI product-state persistence ownership; wire-level API taxonomy/schemas/catalog;
LLM/Push/Video/Payment vendors, cloud/hosting, secret-store mechanism; Kashier's exact recurring-agreement
interval compatibility with the 30-day billing period (external verification gate). Each is an explicit
Node in `decisions.md` and is verified as a *boundary*, never as an invented mechanism.

## 9. Readiness statement

This plan is **assembled and internally consistent** but **not declared READY**. The Plan Readiness Gate
is evaluated in Stage 14 (`Plan Validation`), covering the 12 quality dimensions (5 critical) and the
readiness checklist.
