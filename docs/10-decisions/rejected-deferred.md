# Rejected & Deferred Register

> **Authority:** Normative (records intent). These negative decisions are as binding as the positive
> ones: they record what V1 deliberately does **not** do, and why, so intent is not lost.

## Rejected for V1

| Rejected option | Why | Related ADR |
|-----------------|-----|-------------|
| Layered monolith as the primary structure | Does not structurally protect the domain boundaries | ADR-001 |
| Microservices | Serve only the lowest-ranked driver; fight isolation & simplicity; unoperable at team size | ADR-001 |
| Separate AI service | No present driver for AI-specific scaling/deployment; a dedicated AI Engineer is not sufficient reason | ADR-002 |
| Separate Teacher/Student API products | Duplicates semantics, invites divergence (the SentinelX failure mode) | ADR-003 |
| Per-teacher physical databases | Unnecessary operational cost; logical isolation with central enforcement suffices | ADR-004 |
| Grade-stamping column on monthly records | Redundant: Grade is immutable within an Enrollment, so context is safely derived | ADR-007 |
| Synchronous AI operations | Couple user requests to LLM latency; risk hanging requests | ADR-006 |
| Streaming as the V1 async-operation transport | Not required in V1; polling is sufficient | ADR-006 |
| Role-only authorization (RBAC) | Cannot express tenant + ownership scoping | ADR-010 |
| Universal idempotency across the API | Unnecessary complexity for naturally-safe operations | ADR-011 |
| A separate worker service/microservice | Contradicts the one-deployable decision without a present driver | ADR-012 |

## Deferred (with owner stage)

| Deferred item | Deferred to |
|---------------|-------------|
| Specific cloud / hosting provider | Implementation / Operations |
| Specific LLM, Push, and Video vendors | Implementation / Operations |
| RAG / ingestion implementation for the Knowledge Base | Architecture / AI Engineering |
| OTP / authentication-provider mechanics (claiming) | Implementation / Operations |
| Retention / deletion / privacy & legal policy (incl. minors' data) | Operations follow-up (before treated as binding) |
| API deprecation / backward-compatibility policy | API documentation stage |
| Numeric RPO / RTO targets | Operations (only if a business requirement emerges) |
| Native / cross-platform mobile app | V2 |
| More granular video-targeting mechanics | Requirements / Contracts detail |
| Final serialized API schemas & endpoint catalog | API documentation stage |
| Notification content, delivery lifecycle | Requirements / Cross-cutting detail |
| Homework upload/annotation | Fenced feasibility gate (outside V1 Definition-of-Done) |
| Teacher authentication mechanism (credentials/OTP/token/provider) | Implementation |
| Secure Teacher→Student invitation/access mechanism | System (unresolved) / Implementation |

### Resolved since the table above was first written

| Item | Resolution |
|------|------------|
| ~~Teacher Environment provisioning trigger & cardinality (one vs. many)~~ | **Cardinality resolved by ADR-013** — permanent one Teacher Account : one Teacher Environment (INV-9). The **provisioning-trigger mechanism** (automatic vs. explicit action) remains open, deferred to Implementation. |
| ~~Commercial mechanics: pricing, plans, billing provider/gateway, invoicing~~ | **Resolved by the commercial-design pass** — see `01-product/commercial-model.md` (3 plans, exact prices/caps/features; Kashier as payment provider per ADR-015). Invoicing/tax requirements and refund policy remain open (recorded in `commercial-model.md` §Open items), as does Kashier's own merchant-onboarding/invoicing mechanics. |
| ~~Free Trial exact duration; renewal & cancellation mechanics~~ | **Resolved by the commercial-design pass** — 16-day trial, 250-student cap, no card, no auto-convert; 30-elapsed-day billing period; auto-renewal; cancel-at-period-end (`01-product/commercial-model.md`). Exact failed-renewal retry/grace numbers remain open. |
| Access-not-granted behavior: suspension / grace / read-only | **Principle resolved, exact mechanics remain open.** The access-not-granted principle (account/data never destroyed; auth/billing/export access preserved; Backend-enforced gating) is decided (`01-product/commercial-model.md` §Access-not-granted principle, ADR-018). The exact student-facing restricted-access behavior and the complete teacher read-only ruleset remain **System (unresolved) / Operations**. |

### Newly deferred (Kashier/billing-specific; not decided here)

| Deferred item | Deferred to |
|---------------|-------------|
| Exact failed-renewal retry count/schedule; grace-period duration | Commercial-design follow-up |
| Student-facing restricted-access behavior; teacher read-only ruleset (exact scope) | System (unresolved) / Operations |
| Repeat-trial / trial-abuse controls | Commercial-design follow-up |
| AI usage quotas / cost controls | Commercial-design follow-up |
| Upgrade/downgrade timing; proration policy | Commercial-design follow-up |
| Refund eligibility / process | Commercial-design follow-up |
| Existing-subscriber treatment on future price changes | Commercial-design follow-up |
| Invoice/receipt/tax requirements | Commercial-design follow-up / legal |
| Kashier's exact recurring-agreement consent requirements; ambiguous-outcome recovery procedure | External verification (Kashier) |
| Whether Kashier's recurring-agreement product supports an exact 30-elapsed-day interval vs. only calendar-month | External verification (Kashier) — **launch/design gate** |
| Concrete production scheduling/monitoring for renewal/reconciliation jobs | Operations |

## Product decisions that superseded the original brief

Recorded for provenance (detailed in the relevant documents):

- **AI Study Assistant identity** — redefined from "scoped to the student's available content" to a
  **general educational tutor** grounded in the central curated KB, not scoped to the student's
  records/identity. Intentional supersession.
- **Grade owns the fee** (not the Group) — corrects the brief's implied Group-level fee/schedule.
  See INV-5.
- **Isolation is on records, not identity** — the student identity may be global; records are
  teacher-scoped. Refines the brief's "data isolated between teachers." See INV-7.
- **"New quiz/activity" notification removed** — contradicted the student-initiated AI-Quiz model; no
  teacher-published quiz exists in V1.
