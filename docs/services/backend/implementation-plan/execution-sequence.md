# Execution Sequence — Strategy, Waves, Gates

> **Authority:** Layer 4 (derived from the dependency graph + state model). Waves are the execution
> projection; they do **not** reduce scope. Coverage of full V1 is preserved; phasing is dependency-driven.

## Strategy

**Foundation-first + Risk overlay.** Rationale: the typed graph shows the platform floor + enforcement
substrate as a repeated precondition beneath every module (driver #1 = tenant isolation, structural), and
the two highest engineering risks (isolation-enforcement mechanism, Outbox atomicity) are pulled forward as
SPIKEs before their consumers. A limited vertical slice (Fast-Session) proves the seams end-to-end once the
foundation exists. Big-bang is rejected (ignores the graph).

## Deferred-mechanism rule (applies across all waves)

A **SEAM-READY** WU may establish and consume its documented seam within its wave. Its fenced,
mechanism-specific portion remains **explicitly deferred** and becomes executable only after its governing
decision Node is resolved. Fenced mechanisms are **not** ordinary implementation tasks and get **no**
separate wave; they are deferred sub-tasks inside the owning WU's wave and do not gate the wave.

## Waves (exactly-once WU ownership)

| Wave | WUs (execution owners) | Count | Exit gate |
|---|---|---|---|
| **W0 — Investigate** | FND-03, FND-08 | 2 | **G-SPIKE** — isolation + hand-off mechanisms validated vs all-paths/atomicity |
| **W1 — Platform Floor** | FND-01, FND-02, FND-11, FND-12, EXT-01, EXT-02, EXT-03 | 7 | **G-FLOOR** — deployable (two roles) + persistence + provider seams exist |
| **W2 — Enforcement Substrate** | FND-04, FND-05, FND-06, FND-07, FND-09, FND-10 | 6 | **G-GUARD (critical)** — isolation/authz/invariant/atomic-hand-off proven by negative suites |
| **W2.5 — Lifecycle Seams (∥)** | TAL-01, TAL-02, TAL-04 | 3 | **G-SEAM** — authenticated-actor / env-established / access-input seams defined & consumable (mechanisms fenced) |
| **W3 — Identity Core** | IE-01, IE-02, IE-03, IE-04, IE-05, TAL-03, AUTH-01 | 7 | **G-IDENTITY** — Enrollment keystone + INV-1..6 proven; capability provider ready; claiming + introduction seams ready |
| **W4 — Educational + Financials** | EO-01, EO-02, EO-03, EO-05, FIN-01, FIN-02, CON-01, CON-02 | 8 | **G-EDU** — session lifecycle + capture/correction + payment + video/KB authoring |
| **W5 — Async & Cross-Module** | RUN-02, AI-01, EO-04, CON-03 | 4 | **G-ASYNC** — spine + LLM seam + event emission failure-tolerant |
| **W6 — AI/Eval/Notify + Fast-Session** | AI-02, AI-03, SE-01, SE-02, SE-03, SE-04, NOT-01, NOT-02, RUN-01 | 9 | **G-EXPERIENCE** — Quiz/State-rec/State/Rating/Notifications + per-tap bar |
| **W7 — API Surface & Ops** | API-01, OPS-01, OPS-02 | 3 | **G-CONTRACT** — unified `/api/v1` enforcement + environments/backup |
| **Total** | | **49** | |

**Parallelism note (W2.5):** W2.5 runs parallel to the tail of W2 because TAL-01/02/04 depend only on the
platform floor + the context/authz seam, not on completion of their fenced mechanisms. This is graph-derived,
**not** a universal independence claim: **TAL-03 and AUTH-01 are in W3** because they have a real prerequisite
on IE-01 (the existing Student identity model).

## Gate chain

`G-SPIKE → G-FLOOR → G-GUARD (critical) → G-SEAM → G-IDENTITY → G-EDU → G-ASYNC → G-EXPERIENCE → G-CONTRACT`

**G-GUARD is the critical enforcement gate:** no module may begin persistence before tenant-isolation and
invariant enforcement are proven by the negative suites (driver #1). Each gate requires the wave's WUs
*verified* (not merely implemented) at their documented boundary; fenced mechanism portions are explicitly
excluded from the gate and tracked as deferred.

## Consumption vs execution (exactly-once ownership)

Foundational capabilities are implemented once and **consumed** later without a second WU:
FND-10 (owner W2) is consumed by EO-04 (W5), NOT-01/NOT-02 (W6); FND-09 (W2) by RUN-02/CON-03 (W5), NOT-01 (W6);
IE-04 (W3) by FIN/SE/CON/AI; RUN-02 (W5) by AI-02/03 (W6); EXT-01/02/03 (W1) by AI-01/NOT-01/CON-01. These are
consumption edges, not re-executions.

## Integrity

Waves respect the acyclic typed graph; SPIKEs precede consumers; SEAM-READY WUs enter on their seam; no
DECISION node forces a consumer BLOCKED; every wave boundary is a real dependency boundary (no narrative
phasing). **PASS.**
