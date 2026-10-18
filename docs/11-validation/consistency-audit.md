# Validation — Consistency Audit

> **Authority:** Descriptive (documentation quality control).
> **Purpose:** record the contradictions caught and resolved during discovery (with provenance), and
> the open items that remain non-blocking with owners.

## Contradictions caught & resolved (with provenance)

| Issue | Resolution |
|-------|------------|
| Group-vs-Grade fee | Fee owned by **Grade**, not Group (INV-5). Corrects the brief's implied Group fee. |
| "New quiz/activity" notification vs. student-initiated AI Quiz | Notification **removed**; no teacher-published quiz in V1. |
| Brief's AI-student-scoping vs. general-tutor decision | AI Assistant redefined as a **general tutor** on the central KB (intentional supersession). |
| Isolation vs. global identity | Isolation applies to **records**, not identity; student identity may be global (INV-7). |
| Multi-Grade membership ambiguity | A student belongs to **exactly one Grade** per Enrollment (INV-3). |

All resolved with provenance; none remain open. See
[`../10-decisions/rejected-deferred.md`](../10-decisions/rejected-deferred.md).

## Open items (non-blocking, with owners)

| Item | Owner stage |
|------|-------------|
| Homework feasibility gate | Fenced from V1 Definition-of-Done |
| Retention / deletion / privacy policy | Operations follow-up |
| Vendor selections (cloud/LLM/push/video) | Implementation / Operations |
| RAG / ingestion design | Architecture / AI Engineering |
| OTP / auth-provider mechanics | Implementation |
| Notification content / delivery lifecycle | Requirements / Cross-cutting detail |
| Video-targeting granularity | Requirements / Contracts detail |
| Serialized API schemas & endpoint catalog | API documentation stage |
| API deprecation policy · numeric RPO/RTO | Deferred (until a requirement emerges) |

**No blocking inconsistencies.** These items are correctly deferred; none contradicts validated
knowledge.

## Lifecycle correction pass (upstream Teacher/commercial lifecycle)

A later correction pass repaired the upstream lifecycle gaps found by the Story-Reconstruction audit,
additively and without altering already-correct areas.

**Added (system-level lifecycle only):**
- `03-domain/actor-lifecycles.md` — Teacher account lifecycle, Teacher-Environment establishment,
  empty→usable onboarding framing, and the Teacher→Student *connection* into the existing claiming
  model.
- `01-product/access-lifecycle.md` — Free Trial → Subscription access lifecycle (existence & purpose;
  commercial mechanics deferred).
- Lifecycle terms in `00-overview/glossary.md`; product-entry framing in `system-overview.md`; a
  Teacher-authentication existence note in `08-cross-cutting/security-authz.md`.

**Preserved unchanged (confirmed still correct):** the Student identity/claiming model
(teacher-created → unclaimed → phone-based claim → authenticated; global Student vs. teacher-scoped
Enrollment), the educational domain/runtime/data/contracts, authorization principles, invariants, and
all ADRs. No existing decision was reopened.

**Deferred items remaining open** (in `../10-decisions/rejected-deferred.md`): Teacher auth mechanism;
Environment provisioning **trigger** mechanism (cardinality itself is now resolved by
`ADR-013-permanent-environment-cardinality.md`/INV-9); secure Teacher→Student invitation mechanism;
commercial-mechanics sub-items not fixed by the commercial-design pass (retry/grace numbers,
refunds/proration, student-facing restricted-access behavior) — see `01-product/commercial-model.md`
§Open items. Pricing/plans/trial duration/renewal/cancellation are **no longer** deferred; they are
decided in `01-product/commercial-model.md`.

**Consistency:** the new lifecycle connects to existing states without contradiction — it terminates
exactly at the "authenticated Teacher operating an environment" precondition the capability docs
already assumed, and enters the Student model exactly at its existing "teacher-created" origin.
