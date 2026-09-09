# Change & Deviation Model

> **Authority:** Layer 4 (derived). Defines how the plan absorbs reality-vs-plan divergence and records the
> planning history. Reality may differ from the plan; divergence is handled explicitly, never silently.

## Deviation protocol

```
Discovery → Impact Analysis → Decision → Plan Update → Continue
```

On any deviation (undocumented infrastructure, conflicting assumption, changed external behavior, unexpected
constraint, architectural mismatch, missing capability, new dependency), determine whether it requires a change
to: the Work Unit, the dependency graph, verification, the Documentation, an ADR/decision, or replanning. A
documentation-level cause is **escalated** (System/Backend own their truth); it is not absorbed into the plan.
The blocking graph must remain acyclic after any change, and traceability must remain intact.

## Deviation classification

- **CLEAR** → planning proceeds.
- **UNCERTAIN** → investigation / SPIKE.
- **CONFLICTING** → explicit decision required.
- **SYSTEM-IMPACTING** → escalate to the owning documentation layer.
- **INFEASIBLE** → replanning / scope decision.

## Change log (planning history)

| # | Change | Type | Resolution |
|---|---|---|---|
| C-01 | WU count reconciliation 41 → 43 (ID-by-ID enumeration corrected earlier inconsistent counts) | Bookkeeping | Canonical 43 adopted; no scope change |
| C-02 | **ISSUE-08-01 / ESC-01** — Teacher account/auth/Environment lifecycle was a hidden precondition, absent from docs | SYSTEM-IMPACTING → escalated | Documentation corrected additively; plan reconciled → WS-TAL + 4 Nodes; resolved at documentation-gap level |
| C-03 | Lifecycle documentation delta (System: actor-lifecycles, access-lifecycle + notes; Backend: TAL-1..5, DAT-4, EX-3, AL-2, BD-21..24) | Additive delta | Surgical reconciliation; ~90% of graph preserved; new edges only |
| C-04 | State-semantics distinction (BLOCKED vs SEAM-READY) applied | Classification | TAL-01..04 + AUTH-01 reclassified BLOCKED→SEAM-READY; EXT/OPS/FND-12 labelled SEAM-READY; 0 BLOCKED |
| C-05 | `default-open` withdrawn from TAL-04 | Correction | TAL-04 exposes only the abstract access-state input; no access policy asserted |
| C-06 | WU count reconciliation 47 → 49 (EO-05, FIN-02 were canonical but omitted from a Stage 11 workstream subtotal and the wave table) | Bookkeeping | Canonical 49 adopted; no scope change; both assigned to W4 |

## Current canonical baseline (post-reconciliation)

- **49 Work Units** = **36 READY · 11 SEAM-READY · 2 SPIKE · 0 BLOCKED**; **9 Nodes**.
- Waves W0–W7 (with W2.5 parallel) — exactly-once ownership.
- Strategy: Foundation-first + Risk overlay. Gates: G-SPIKE → … → G-CONTRACT (G-GUARD critical).

## Invariants preserved across all changes

Student identity/claiming model; composite authorization; tenant isolation + `teacher_environment_id`
semantics; all ADRs (001–012); student fee tracking; the Teacher-commercial-access vs student-fee-tracking
distinction; and all documented negative space. No change reopened settled documentation decisions or resolved
a fenced mechanism.

## Open items still tracked (not deviations — planned fences)

All 9 Nodes in `decisions.md` remain open/fenced and are tracked here as future decision points; resolving any
of them triggers the deviation protocol above (impact analysis → plan update) for the WUs it unblocks.
