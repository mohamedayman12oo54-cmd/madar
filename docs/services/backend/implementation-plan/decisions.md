# Decisions & Fenced Nodes

> **Authority:** Layer 4 records planning decisions and **routes** open questions; it never resolves
> system-level truth locally. Resolved stack decisions are authorized inputs; Nodes remain fenced until
> resolved through the appropriate path.

## Resolved stack decisions (D2)

### D2-1 — Runtime / Framework + Process Model → **Python + Django** (RESOLVED)
- **Affected:** OBL-FND-01 (direct); consumed by nearly all WUs. One deployable / two roles (web + worker),
  shared codebase/domain/persistence. **Authority:** Architect/Backend (team-fluency + system drivers).
- **Downstream if changed:** widest — reshapes D2-2 data-access, D2-3 integration, module-boundary
  enforcement style, testing tooling. Decided first.

### D2-2 — Datastore + Data-Access / Isolation / Transaction → **Managed relational (Postgres-class), centralized isolation** (RESOLVED)
- **Affected:** OBL-FND-03/07 + all module persistence; RUN-01/RUN-03 atomicity; CON-02.
- **Commitments:** single logical relational datastore; `teacher_environment_id` uniform isolation context;
  centralized non-bypassable enforcement at the data-access boundary; atomic multi-write; module boundaries/
  invariants preserved. **SPIKE:** FND-03 (isolation-enforcement mechanism, does not reopen the datastore family).
- **Authority:** Architect/Backend + Data. **Downstream if changed:** reshapes INV-7 enforcement, module
  persistence, hand-off shape — decided early after D2-1.

### D2-3 — Async Substrate + Worker Context → **DB-backed job/queue + transactional Outbox + persisted trusted context** (RESOLVED)
- **Affected:** OBL-FND-08/09; RUN-02; NOT-01; CON-03; AI-02/03. Domain state + durable hand-off committed
  atomically in one transaction; at-least-once delivery; idempotent consumers where required; worker trusts
  only server-created persisted context. **SPIKE:** FND-08 (concrete Outbox/job/delivery/idempotency).
- **Authority:** Architect/Backend. **Downstream if changed:** substrate swap is isolated behind the seam
  (ADR-009/EX-2); moving to a broker is a contained, medium-impact change.

### D2-4 — KB Store → **No separate Backend stack decision** (RESOLVED-BY-BOUNDARY)
- KB authoring/lifecycle persistence consumes **D2-2**; AI retrieval/indexing/RAG store remains **fenced**
  behind the AI seam (AI-Module refinement). No separate Backend technology decision.

## Fenced decision Nodes (9) — do not resolve inside the plan

| Node | Fences | Owner / path | Blocks (scope) |
|---|---|---|---|
| **NODE-TeacherAuth** 🔧 | Teacher authentication mechanism (credentials/OTP/token/provider) | Product/Implementation | mechanism portion of TAL-01 (seam unblocked) |
| **NODE-EnvProvision** 🔧🚧 | Environment provisioning trigger + per-Teacher cardinality (one vs many) | System (unresolved)/Implementation | mechanism portion of TAL-02 (empty-state seam unblocked) |
| **NODE-Invitation** 🔧 | Secure Teacher→Student invitation mechanism | System (unresolved)/Implementation | mechanism portion of TAL-03 (connection unblocked) |
| **NODE-AccessBehavior** 🔧 | Access-not-granted behavior (suspend/grace/read-only) + commercial mechanics + source of access state | Commercial-design / System | mechanism/policy portion of TAL-04 (input seam unblocked) |
| **NODE-OTP** 🔧 | Student claiming OTP/verification provider | Security/Ops | mechanism portion of AUTH-01 (claiming seam unblocked) |
| **NODE-AIOwnership** 🚧 | AI product-state persistence *ownership* (which module) | Domain/AI-Module | ownership commitment of SE-04/AI-02/AI-03 (behavior unblocked) |
| **NODE-WireAPI** 📄 | Serialized API taxonomy/HTTP codes/schemas/endpoint catalog | API-documentation stage | serialized portion of API-01/FND-07 (semantics unblocked) |
| **NODE-Vendors** 🏭 | LLM/Push/Video vendors, cloud/hosting, secret-store mechanism | Ops/Commercial | vendor adapters of EXT-*/OPS-*/FND-11/12 (seams unblocked) |
| **NODE-StudyAssistant** 🚧 | Study Assistant interaction model (OBL-AI-05) | System/Product | capability retained in V1 baseline; no implementation WU until interaction model defined |

> **Rule:** a Node fences a *mechanism/policy/ownership*, never a *boundary*. Its consumer WU is SEAM-READY
> (or READY with a fenced sub-boundary), not BLOCKED. No Node is resolved to make the plan more concrete.

## Escalation record — ESC-01 (RESOLVED via documentation)

- **Raised (Stage 8, ISSUE-08-01):** the Teacher account/authentication/Environment-establishment lifecycle
  was a hidden precondition of FND-05 and the IE tree, absent from the then-current System + Backend docs.
- **Routing:** documentation-gap escalation (System owns actors/scope/domain/identity; Backend specializes).
- **Resolution:** System Documentation added `03-domain/actor-lifecycles.md` + `01-product/access-lifecycle.md`
  (+ existence notes + deferred items); Backend added `01-scope/teacher-access-lifecycle.md` (TAL-1..5),
  DAT-4, EX-3, AL-2, BD-21..24. Purely additive; no existing decision reopened. Plan reconciled surgically →
  WS-TAL (4 SEAM-READY WUs) + 4 new Nodes. ISSUE-08-01 resolved at the documentation-gap level.

## Standing escalation rule

Any planning discovery that would change a system boundary, invariant, external/client contract, the
tenant/isolation model, or an inherited ADR is **escalated** to the owning documentation layer — never
resolved locally in this plan.
