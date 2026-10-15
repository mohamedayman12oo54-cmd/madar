# Work Breakdown — 49 Canonical Work Units

> **Authority:** Layer 4 (derived). Each WU is a **bounded engineering outcome**, not a file/class/ticket.
> **Frozen:** IDs, workstreams, outcomes, states, wave assignment are canonical (Stage 12). This file
> represents them; it does not redesign them.
> **State:** READY · SEAM-READY · SPIKE · BLOCKED(none). **Fence:** 🔧 mechanism · 🏭 vendor/infra · 📄 downstream-doc · 🚧 governance.
> **Dependency notation:** `prereq → this` types are BLOCK/CONTRACT/DATA/ENV/DECISION/EXTERNAL/VERIF (see `dependencies.md`).
> Foundation floor (FND-01/02) and enforcement substrate (FND-04/05/06/07) are **shared preconditions**
> consumed by all teacher-scoped WUs; they are not repeated as per-WU edges.

**Totals:** 49 WU = 36 READY · 11 SEAM-READY · 2 SPIKE · 0 BLOCKED. Per-workstream: FND 12 · IE 5 · EO 5 · FIN 2 · SE 4 · CON 3 · AI 3 · NOT 2 · RUN 2 · API 1 · AUTH 1 · EXT 3 · OPS 2 · TAL 4.

---

## WS-FND — Foundation & Platform (12)

### FND-01 — Application skeleton (web + worker) · READY · W1
- **Outcome:** Django application running as one deployable in two roles (web/API + worker), sharing codebase/domain/persistence.
- **Source:** OBL-FND-01 ← ADR-001/012 (Sys), execution-model (BE), D2-1.
- **In scope:** project/runtime skeleton, role split. **Out:** any business logic, module code.
- **Prereqs:** — (root). **Consumers:** platform floor for all WUs.
- **Verify:** both roles run from one codebase/domain/persistence; worker is not a separate service. Method: integration/smoke. Evidence: CI.

### FND-02 — Persistence foundation + migration baseline · READY · W1
- **Outcome:** Relational persistence + migration tooling + transaction-coordination conventions supporting atomic multi-write.
- **Source:** OBL-FND-07 ← consistency/data-model (Sys+BE), D2-2.
- **In scope:** DB connection, migration baseline, txn conventions. **Out:** per-module schema.
- **Prereqs:** FND-01 (ENV). **Consumers:** all persisting WUs; FND-04/09/10.
- **Verify:** atomic multi-write; migrations apply/rollback. Method: integration. Evidence: CI.

### FND-03 — SPIKE: isolation-enforcement mechanism · SPIKE · W0
- **Outcome:** Validated mechanism that prevents cross-tenant access on every path, measured against INV-7/all-paths (application/data-access scoping ± DB row-level defense-in-depth). Does **not** reopen the datastore family (D2-2).
- **Source:** OBL-FND-03 ← ADR-004/007·INV-7 (Sys), DAT-1 (BE).
- **Prereqs:** — . **Feeds:** FND-04. **Verify (spike):** no leak on any path under negative suite. Evidence: spike report + tests.

### FND-04 — Centralized tenant-isolation data-access boundary · READY · W2
- **Outcome:** Non-bypassable `teacher_environment_id` scoping at the data-access boundary (layer 2), implementing the FND-03 outcome.
- **Source:** OBL-FND-03 ← ADR-004/007·INV-7 (Sys), DAT-1/BND-2 (BE).
- **Prereqs:** FND-03 (BLOCK), FND-02 (BLOCK), FND-05 (CONTRACT). **Consumers:** every teacher-scoped WU.
- **Verify:** teacher-scoped access without established context is refused; no cross-module leak. Method: isolation negative-suite + property/all-paths. Evidence: CI.

### FND-05 — Request boundary: auth context + server-derived tenant/env context + env switch · READY · W2
- **Outcome:** Each request establishes an authenticated actor + server-derived active Teacher-Environment context; explicit switch limited to authorized environments; client cannot supply an arbitrary tenant.
- **Source:** OBL-FND-02 ← ADR-008·api-contract (Sys), EX-1·security-authz (BE).
- **Prereqs:** consumes the authenticated-actor seam from **TAL-01 (CONTRACT)** and the established-environment seam from **TAL-02 (CONTRACT)**. **Consumers:** FND-04/06, API-01, all teacher-scoped WUs.
- **Verify:** client-supplied tenant refused; switch only to authorized envs. Method: integration + negative. Evidence: CI.

### FND-06 — Composite authorization infrastructure · READY · W2
- **Outcome:** Every authz decision = actor + role + authorized environment + relationship/ownership; role alone never sufficient (cross-cutting part).
- **Source:** OBL-FND-04 ← ADR-010 (Sys), BND-2 (BE).
- **Prereqs:** FND-05 (CONTRACT). **Consumers:** resource checks in modules; API-01; consumes access-state input from TAL-04 alongside (not inside).
- **Verify:** authz fails on missing actor/role/env/relationship. Method: unit + integration + negative. Evidence: CI.

### FND-07 — Uniform business-rule/error semantics + invariant-violation rejection · READY · W2
- **Outcome:** Invariant/business-rule violations rejected as business-rule/conflict (no partial, no silent correction); stable machine-readable codes with human messages separate.
- **Source:** OBL-FND-05/06 ← invariants·api-contract (Sys), BR-1·AL-1 (BE).
- **Prereqs:** FND-02 (DATA). **Consumers:** all modules; API-01. **Fenced:** 📄 serialized wire schema (NODE-WireAPI).
- **Verify:** violation → rejection, not partial write. Method: unit + integration + negative. Evidence: CI.

### FND-08 — SPIKE: Outbox + DB job/queue + worker context · SPIKE · W0
- **Outcome:** Validated transactional Outbox + DB-backed job/queue + at-least-once delivery + idempotent consumer + worker trusted-context reconstruction from persisted server-state. Does **not** reopen D2-3.
- **Source:** OBL-FND-08/09·RUN-03 ← ADR-005/012 (Sys), EX-1/2 (BE), D2-3.
- **Prereqs:** — . **Feeds:** FND-09, FND-10. **Verify (spike):** atomicity + at-least-once + idempotent replay + trusted-context. Evidence: spike report + crash/replay tests.

### FND-09 — Async execution substrate + trusted worker-context reconstruction · READY · W2
- **Outcome:** DB-backed job/queue running worker jobs; worker reconstructs trusted context exclusively from server-created persisted state (never client-derived).
- **Source:** OBL-FND-08/09 ← ADR-012 (Sys), EX-2 (BE).
- **Prereqs:** FND-08 (BLOCK), FND-02 (DATA). **Consumers:** RUN-02, NOT-01, CON-03.
- **Verify:** worker context is server-derived only. Method: integration + negative. Evidence: CI.

### FND-10 — Transactional Outbox event hand-off · READY · W2
- **Outcome:** Emitting module commits domain-write + durable event hand-off atomically within its own boundary; async consumption downstream.
- **Source:** OBL-RUN-03 ← ADR-005·consistency (Sys), BND-3 (BE).
- **Prereqs:** FND-08 (BLOCK), FND-02 (DATA). **Consumers (consumption, not re-execution):** EO-04 (emit), NOT-01 (consume), NOT-02 (emit).
- **Verify:** no "record saved, event lost" window. Method: integration + crash/replay. Evidence: CI.

### FND-11 — Configuration & secret handling · READY · W1
- **Outcome:** No hard-coded secrets; no secret exposure via logs/telemetry; config behind Madar-owned interfaces.
- **Source:** OBL-FND-11 ← configuration-secrets (BE). **Fenced:** 🏭 secret-store mechanism (NODE-Vendors).
- **Prereqs:** FND-01. **Verify:** no secret in code/logs. Method: review + integration. Evidence: review record + CI.

### FND-12 — Observability floor · SEAM-READY 🏭 · W1
- **Outcome:** Structured logging + error tracking + basic metrics; explicit observability on async paths; no logging of sensitive student content. Seam implementable now; specific tooling vendor fenced.
- **Source:** OBL-FND-10 ← observability (Sys+BE), BR-3.
- **Prereqs:** FND-01; async-path observability consumes FND-09 (VERIF-soft). **Fenced:** 🏭 tooling vendor.
- **Verify:** async ops/dispatch expose status/failure; no sensitive content logged. Method: integration + review. Evidence: CI + review.

---

## WS-IE — Identity & Enrollment (5) — foundation capability provider

### IE-01 — Student global identity · READY · W3
- **Outcome:** Student as the only non-tenant-scoped entity (name/phone/login, claim state); 0..* Enrollments; may be unclaimed.
- **Source:** OBL-IE-01 ← domain-model·INV-1 (Sys).
- **Prereqs:** substrate. **Consumers:** IE-03, AUTH-01, TAL-03.
- **Verify:** Student carries no tenant key; exists with 0 Enrollments. Method: unit + integration. Evidence: CI.

### IE-02 — Teacher-environment structural entities · READY · W3
- **Outcome:** Academic Year + Grade (owns monthly fee) + Group (belongs to a Grade), all teacher-scoped.
- **Source:** OBL-IE-03 ← domain-model·INV-3/5 (Sys), ADR-007.
- **Prereqs:** substrate; consumes established-environment seam (TAL-02). **Consumers:** IE-03, EO-01/02/05, CON-01, NOT-02.
- **Verify:** Grade owns fee; Group within Grade; teacher-scoped. Method: unit + integration. Evidence: CI.

### IE-03 — Enrollment keystone + membership + INV enforcement · READY · W3
- **Outcome:** Enrollment (Student × Env × Year) with exactly one immutable Grade, group memberships within that Grade; enforces INV-1/2/3/4/6.
- **Source:** OBL-IE-02/03 ← domain-model·INV-1/2/3/4/6 (Sys), FND-05.
- **Prereqs:** IE-01 (BLOCK/DATA), IE-02 (DATA). **Consumers:** IE-04, all enrollment-scoped records.
- **Verify:** one Enrollment per (Student×Env×Year); immutable Grade; membership within Grade. Method: unit + integration + negative. Evidence: CI.

### IE-04 — Internal capability provider (Enrollment/Grade context) · READY · W3
- **Outcome:** Internal capability resolving Enrollment/Grade context for other modules, without direct persistence access (BND-1).
- **Source:** OBL-IE-04 ← building-blocks (Sys), BND-1/internal-contracts (BE).
- **Prereqs:** IE-03 (BLOCK). **Consumers (CONTRACT):** FIN-01/02, SE-*, CON-01, AI-03.
- **Verify:** modules resolve context via capability, not cross-module data reach. Method: contract + integration. Evidence: CI.

### IE-05 — Enrollment / Academic-Year lifecycle · READY · W3
- **Outcome:** Year-end → new Enrollment for continuing/grade-change students; no auto-carry-forward as a domain rule; prior-year records read-only (INV-6).
- **Source:** OBL-IE-05 ← lifecycles·lifecycle-retention·INV-6 (Sys).
- **Prereqs:** IE-03 (DATA). **Verify:** grade change = new Enrollment; prior-year read-only. Method: integration. Evidence: CI.

---

## WS-EO — Educational Operations (5)

### EO-01 — Schedule · READY · W4
- **Outcome:** Recurring expected slot per Group; never prevents recording an off-schedule (ad-hoc) real session.
- **Source:** OBL-EO-05 ← lifecycles·functional (Sys). **Prereqs:** IE-02 (DATA).
- **Verify:** off-schedule session still recordable. Method: integration. Evidence: CI.

### EO-02 — Session Instance lifecycle · READY · W4
- **Outcome:** First-class Session Instance with Planned→Open→Closed→Reopened→Closed; capture only while Open; scheduled or ad-hoc.
- **Source:** OBL-EO-01 ← lifecycles (Sys). **Prereqs:** IE-02 (DATA), EO-01 (CONTRACT, non-blocking).
- **Verify:** transitions valid; capture only while Open. Method: unit + integration. Evidence: CI.

### EO-03 — Attendance & Recitation capture + correction · READY · W4
- **Outcome:** Attendance binary (Present/Absent); Recitation (Studied/Not-Studied persist; Skip records nothing); per Enrollment × Session; correctable; independence across Groups (INV-8).
- **Source:** OBL-EO-02/03 ← functional·INV-8 (Sys). **Prereqs:** EO-02 (BLOCK/DATA), IE-04 (CONTRACT).
- **Verify:** binary attendance; Skip = no record; correction persists; per-session independence. Method: unit + integration + negative. Evidence: CI.

### EO-04 — Absent/Not-Studied event emission · READY · W5
- **Outcome:** On Absent/Not-Studied, EO commits the record + durable event hand-off atomically within its own boundary (consumes FND-10).
- **Source:** OBL-EO-04 ← ADR-005·consistency (Sys), BND-3 (BE). **Prereqs:** EO-03 (BLOCK), FND-10 (BLOCK, consumption).
- **Verify:** record + event atomic. Method: integration + crash/replay. Evidence: CI.

### EO-05 — (Schedule maintenance outcome — see EO-01) · READY · W4
- **Note:** EO-05 is the canonical Schedule Work Unit; its outcome is the recurring-slot capability recorded above under the Schedule heading. Retained as a distinct canonical ID (obligation OBL-EO-05) because its recurring-slot outcome and verification boundary are independent of Session capture (EO-02/03). Exactly-once ownership: **W4**.
- **Source:** OBL-EO-05 ← lifecycles·functional (Sys). **Prereqs:** IE-02 (DATA).
- **Verify:** recurring slot maintainable; does not block off-schedule sessions. Method: integration. Evidence: CI.

> Presentation note: EO-01 and EO-05 both trace to the Schedule obligation family; they are kept as
> the two canonical IDs established in Stage 2/7 and are **not** merged, split, or renamed here.

---

## WS-FIN — Financials (2)

### FIN-01 — Payment record · READY · W4
- **Outcome:** Payment per Enrollment × Calendar Month (paid/unpaid + amount + basic history); record-only.
- **Source:** OBL-FIN-01 ← functional·scope (Sys). **Prereqs:** IE-04 (CONTRACT).
- **Out:** online processing, accounting, partial payments, discounts (negative space).
- **Verify:** monthly record; record-only. Method: unit + integration. Evidence: CI.

### FIN-02 — Grade-owned fee resolution (INV-5) · READY · W4
- **Outcome:** Monthly fee owned by Grade; a second Group in the same Grade creates no additional obligation; resolved via I&E capability.
- **Source:** OBL-FIN-02 ← INV-5 (Sys), BND-1 (BE). **Prereqs:** IE-04 (CONTRACT), FIN-01 (DATA).
- **Verify:** fee via Grade; cross-Group non-duplication. Method: unit + integration + negative. Evidence: CI.

---

## WS-SE — Student Evaluation (4)

### SE-01 — Monthly State + teacher finalization · READY · W6
- **Outcome:** State per Enrollment × Month from {Good, Needs Follow-up, At Risk}; evidence → optional advisory AI → teacher finalizes; AI never authoritative.
- **Source:** OBL-SE-01 ← functional·state-pipeline (Sys). **Prereqs:** IE-04 (CONTRACT).
- **Verify:** teacher finalizes; AI advisory only. Method: integration. Evidence: CI.

### SE-02 — Monthly Rating · READY · W6
- **Outcome:** Teacher-assigned 1–5 Rating per Enrollment × Month, distinct from State; AI does not own it.
- **Source:** OBL-SE-02 ← functional (Sys). **Prereqs:** IE-04 (CONTRACT).
- **Verify:** 1–5 teacher-assigned; distinct from State. Method: unit + integration. Evidence: CI.

### SE-03 — Teacher Private Notes · READY · W6
- **Outcome:** Teacher-authored notes; never visible to the student.
- **Source:** OBL-SE-03 ← functional·security-authz (Sys). **Prereqs:** FND-06 (consumes authz).
- **Verify:** notes never student-visible. Method: integration + negative (student access). Evidence: CI.

### SE-04 — State-recommendation consumption · READY 🚧 · W6
- **Outcome:** SE consumes the advisory State recommendation via the L&AI capability boundary; on failure the teacher finalizes manually.
- **Source:** OBL-SE-04 ← state-pipeline·ADR-006 (Sys). **Prereqs:** AI-03 (CONTRACT), SE-01 (DATA).
- **Fenced:** 🚧 AI product-state persistence *ownership* (NODE-AIOwnership) — behavior implemented/verified; ownership not committed.
- **Verify:** advisory consumed; failure → manual. Method: integration + failure-injection. Evidence: CI.

---

## WS-CON — Content (3)

### CON-01 — Video metadata + targeting · READY · W4
- **Outcome:** Video metadata + targeting + external reference (blob external); students access targeted videos; upload→target→watch.
- **Source:** OBL-CON-01 ← functional·data-model·external-interfaces (Sys). **Prereqs:** IE-04 (CONTRACT), EXT-03 (CONTRACT).
- **Verify:** targeting resolves; blob external. Method: integration. Evidence: CI.

### CON-02 — KB authoring + lifecycle · READY · W4
- **Outcome:** KB authoring API for the Content Maintainer (create/edit/manage/publish) + app-level lifecycle (draft→published; published-only authoritative); Maintainer isolated from educational records.
- **Source:** OBL-CON-02 ← scope·KB-ops (Sys+BE). **Prereqs:** FND-06 (BLOCK — Maintainer authz isolation).
- **Verify:** only published authoritative; Maintainer has no educational-record access. Method: integration + negative. Evidence: CI.

### CON-03 — KB publish → processing orchestration · READY 🚧 · W5
- **Outcome:** Backend owns the publish→processing orchestration boundary (trigger/lifecycle/failure where it touches AI-readiness); indexing/RAG behind the AI seam.
- **Source:** OBL-CON-03 ← KB-seam·KB-ops·BR-3 (BE). **Prereqs:** CON-02 (BLOCK), FND-09 (CONTRACT/BLOCK).
- **Fenced:** 🚧 RAG/retrieval store behind AI seam (NODE-AIOwnership-adjacent).
- **Verify:** publish orchestration observable where it affects AI-readiness. Method: integration. Evidence: CI.

---

## WS-AI — Learning & AI (3)

### AI-01 — L&AI capability + LLM seam · READY · W5
- **Outcome:** Learning & AI is the sole LLM-seam crosser; exposes internal capability (trusted context + bounded source + result/failure); no other module touches the LLM.
- **Source:** OBL-AI-01 ← ADR-002·external-interfaces (Sys), AI-contract (BE). **Prereqs:** EXT-01 (CONTRACT/BLOCK).
- **Verify:** only L&AI crosses the seam. Method: integration + architecture check. Evidence: CI + review.

### AI-02 — AI Quiz operation · READY 🚧 · W6
- **Outcome:** Student-initiated quiz from teacher content; async submit→poll; quiz persisted before answering; auto-scored where allowed; no partial on failure; idempotent submission.
- **Source:** OBL-AI-02 ← ai-quiz·functional·ADR-006/011 (Sys). **Prereqs:** RUN-02 (BLOCK), AI-01 (CONTRACT), CON-01 (DATA/CONTRACT).
- **Fenced:** 🚧 persistence ownership (NODE-AIOwnership).
- **Verify:** no partial quiz; idempotent submit; auto-score. Method: integration + failure-injection + idempotency. Evidence: CI.

### AI-03 — State recommendation operation · READY 🚧 · W6
- **Outcome:** On-demand advisory recommendation; async; failure → unavailable; non-authoritative.
- **Source:** OBL-AI-03 ← state-pipeline·ADR-006 (Sys). **Prereqs:** RUN-02 (BLOCK), AI-01 (CONTRACT), EO-03 (DATA), AI-02 (DATA, non-blocking evidence). **Pairs:** SE-04.
- **Fenced:** 🚧 persistence ownership (NODE-AIOwnership).
- **Verify:** advisory, async, non-authoritative. Method: integration + failure-injection. Evidence: CI.

---

## WS-NOT — Notifications (2)

### NOT-01 — Notification consumption + dispatch · READY · W6
- **Outcome:** Async consumption of durable hand-offs; dispatch + retry; Push integration; internal worker job; fired-and-forgotten (correction does not retract a sent notification; a new Absent/Not-Studied may fire a new event).
- **Source:** OBL-NOT-02/03/04 ← ADR-005 (Sys), BND-3 (BE). **Prereqs:** FND-09 (BLOCK), FND-10 (BLOCK, consumption), EXT-02 (CONTRACT).
- **Verify:** async consumption; fired-and-forgotten; internal-only observability. Method: integration. Evidence: CI.

### NOT-02 — Non-auto event emission wiring · READY · W6
- **Outcome:** Emit new-video, rating-published, teacher-manual-broadcast events via hand-off; five-event catalog only (no "new quiz").
- **Source:** OBL-NOT-01 ← functional·PD-4 (Sys). **Prereqs:** FND-10 (CONTRACT), CON-01/SE-02/IE-02 (DATA sources).
- **Verify:** exactly the five events; no teacher-quiz event. Method: integration. Evidence: CI.

---

## WS-RUN — Runtime flows (2)

### RUN-01 — Fast-Session synchronous per-tap path · READY · W6
- **Outcome:** Per-tap durable write; sync path = authn/authz+ctx → validate → persist → (Absent/Not-Studied) atomic record+event → return; no delivery/AI/batch on the sync path; close = transition not flush; Skip records nothing.
- **Source:** OBL-RUN-01 ← BR-2·fast-session (BE), ADR-005·quality (Sys). **Prereqs:** EO-02/03/04 (BLOCK, composition) + substrate.
- **Verify:** no delivery/AI/batch on sync path; per-tap durable; qualitative bar (immediate at 40–50/group, mid-range phone; no numeric SLA). Method: integration + perf-smoke. Evidence: CI.

### RUN-02 — Async-operation spine · READY · W5
- **Outcome:** Reusable spine: submit → idempotency → persist op + trusted ctx → ack(op id) → worker reconstruct → Processing → invoke L&AI → persist result/failure → terminal (Succeeded|Failed); polling.
- **Source:** OBL-RUN-02 ← ADR-006/011·api-contract (Sys), async-operations (BE). **Prereqs:** FND-09 (BLOCK), AI-01 (CONTRACT), FND-05 (CONTRACT). **Consumers:** AI-02, AI-03.
- **Verify:** submit→poll→terminal; idempotent submit; context reconstructed. Method: integration + failure-injection. Evidence: CI.

---

## WS-API — API surface (1)

### API-01 — Unified REST API `/api/v1` + contract enforcement · READY 📄 · W7
- **Outcome:** Single versioned API for all three clients; enforces server-derived tenant, one active env per student-context (no cross-env merge), composite authz, submit-poll async, selective idempotency. Auth precedes; environment availability is a lifecycle state; access-state may gate (AL-2).
- **Source:** OBL-API-01/02 ← ADR-003·api-contract (Sys), external-api-alignment (BE). **Prereqs:** FND-05/06/07 (CONTRACT), RUN-02 (CONTRACT), TAL-04 (CONTRACT, access-state input).
- **Fenced:** 📄 serialized endpoint catalog/schemas (NODE-WireAPI). Per-resource endpoints delivered within the owning module WUs.
- **Verify:** contract rules enforced; no cross-env merge. Method: contract + integration + negative. Evidence: CI.

---

## WS-AUTH — Authentication / Claiming (1)

### AUTH-01 — Phone-based student claiming · SEAM-READY 🔧 · W3
- **Outcome:** Claiming establishes access to the **existing** global Student identity (no new identity, no record rebuild). Student model preserved exactly.
- **Source:** OBL-AUTH-02 ← security-authz·glossary (Sys). **Prereqs:** IE-01 (BLOCK/DATA), FND-05 (CONTRACT).
- **Fenced:** 🔧 OTP/identity-verification provider (NODE-OTP). Seam (claiming/verification boundary) implementable; provider deferred.
- **Verify:** claiming reaches existing identity; no rebuild. Method: integration + regression (claiming preserved). Evidence: CI.

---

## WS-EXT — External interfaces (3)

### EXT-01 — LLM interface · SEAM-READY 🏭 · W1
- **Outcome:** Madar-owned LLM interface consumed only by L&AI; async/failure-tolerant; model stays outside the boundary.
- **Source:** OBL-EXT-01 ← external-interfaces·ADR-009/002/006 (Sys). **Fenced:** 🏭 vendor. **Prereqs:** FND-01.
- **Verify:** interface stable; L&AI-only. Method: contract + integration. Evidence: CI.

### EXT-02 — Push Delivery interface · SEAM-READY 🏭 · W1
- **Outcome:** Madar-owned Push interface; stores device tokens/registrations; delivery external/async, failure-isolated.
- **Source:** OBL-EXT-02 ← external-interfaces·ADR-009/005 (Sys). **Fenced:** 🏭 vendor. **Prereqs:** FND-01.
- **Verify:** token storage; failure-isolated delivery seam. Method: contract + integration. Evidence: CI.

### EXT-03 — Video Storage/Delivery interface · SEAM-READY 🏭 · W1
- **Outcome:** Madar-owned Video interface; metadata + reference; blob external.
- **Source:** OBL-EXT-03 ← external-interfaces·ADR-009 (Sys). **Fenced:** 🏭 vendor. **Prereqs:** FND-01.
- **Verify:** metadata/reference seam; blob external. Method: contract + integration. Evidence: CI.

---

## WS-OPS — Operations (2)

### OPS-01 — Three-environment deployment + guarantee-parity · SEAM-READY 🏭 · W7
- **Outcome:** dev/staging/prod, each running both roles; security/correctness guarantees hold with equal strength across environments and roles.
- **Source:** OBL-OPS-01·FND-12 ← deployment·ADR-001/012 (Sys), OP-PARITY (BE). **Fenced:** 🏭 cloud/hosting. **Prereqs:** FND-01/12 (BLOCK/CONTRACT).
- **Verify:** both roles per env; guarantee-parity. Method: integration + ops check. Evidence: CI + ops record.

### OPS-02 — Backup / recovery enablement · SEAM-READY 🏭 · W7
- **Outcome:** Managed datastore backup + PITR enabled in production; recovery practically verifiable; no numeric RPO/RTO; no bespoke DR.
- **Source:** OBL-OPS-02 ← backup-recovery (Sys+BE). **Fenced:** 🏭 vendor/procedure. **Prereqs:** FND-02 (DATA), OPS-01 (ENV).
- **Verify:** backups enabled; recovery verifiable. Method: ops verification. Evidence: ops record.

---

## WS-TAL — Teacher Access & Lifecycle (4) — boundary responsibilities, mechanisms fenced

### TAL-01 — Teacher account + authenticated actor context · SEAM-READY 🔧 · W2.5
- **Outcome:** Represent the Teacher as a distinct authenticatable actor and produce the authenticated-Teacher actor context the composite model + capability docs assume. Separate path from student entry; student model unchanged.
- **Source:** OBL-TAL-01/02 ← TAL-1·actor-lifecycles·security-authz (Sys+BE), BD-21. **Prereqs:** FND-01, FND-05 seam. **Consumers:** FND-05 (CONTRACT).
- **Fenced:** 🔧 Teacher authentication mechanism (NODE-TeacherAuth). Seam = "authenticated Teacher actor context must exist before capability requests are authorized."
- **Verify:** capability request refused without authenticated Teacher context; actor distinct from student; **no auth mechanism assumed**. Method: contract + integration + regression. Evidence: CI.

### TAL-02 — Environment establishment + initial empty state · SEAM-READY 🔧 · W2.5
- **Outcome:** Recognize Environment establishment/origin and initial **empty** state (no years/grades/groups/enrollments/records) as a real lifecycle point; isolation semantics unchanged. **Cardinality is now resolved** — exactly one Environment per Teacher Account, permanently (ADR-013/INV-9).
- **Source:** OBL-TAL-03 ← TAL-2·DAT-4 (BE), actor-lifecycles (Sys), BD-22; cardinality resolved by ADR-013. **Prereqs:** FND-02, FND-04 seam. **Consumers:** FND-05 (CONTRACT), IE-02 (DATA).
- **Fenced:** 🔧 provisioning trigger only (NODE-EnvProvision). Cardinality is no longer fenced.
- **Verify:** established Environment is empty; isolation holds from origin; exactly-one-per-account cardinality holds (pending the implementation follow-up — OneToOneField migration, data-integrity check, test-fixture update, per ADR-013 §Consequences); **trigger mechanism not asserted**. Method: integration + isolation negative-test. Evidence: CI.

### TAL-03 — Teacher→Student introduction (bridge) · SEAM-READY 🔧 · W3
- **Outcome:** Represent the Teacher-side introduction/association as the entry point into the **existing** claiming model — a connection, not a new identity/account system.
- **Source:** OBL-TAL-04 ← TAL-4 (BE), actor-lifecycles (Sys), BD-23. **Prereqs:** IE-01 (CONTRACT — uses existing student-identity model).
- **Fenced:** 🔧 secure invitation mechanism (NODE-Invitation). Boundary only; claiming model unchanged; **not expanded** into an invitation subsystem.
- **Verify:** introduction enters existing claiming unchanged (regression). Method: regression + contract. Evidence: CI.

### TAL-04 — Abstract access-state input at the access-decision boundary · SEAM-READY 🔧 · W2.5
- **Outcome:** Represent an abstract access-state input ("does this Teacher currently have access?") consumed **alongside and prior to** composite authorization. Not a billing architecture.
- **Source:** OBL-TAL-05 ← TAL-5·AL-2·DAT-4·security-authz (BE), access-lifecycle (Sys), BD-24. **Prereqs:** FND-05, FND-06 seam. **Consumers:** API-01 (CONTRACT), FND-06 (alongside).
- **Fenced:** 🔧 access-not-granted behavior (suspend/grace/read-only) + commercial mechanics + source of access state (NODE-AccessBehavior). **No `default-open` or any access policy is introduced or implied.**
- **Verify:** access-state consulted as an input, separate from & prior to authz; **no billing / no not-granted behavior asserted**. Method: contract + integration. Evidence: CI.
