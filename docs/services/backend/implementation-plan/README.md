# Madar Backend — Implementation Plan v1.0

> **Nature:** A traceable execution model **derived from** the approved Madar System + Backend Service
> Documentation. It defines *what must be done* to realize the documented Backend, its dependencies,
> execution strategy, verification paths, and operational guidance.
> **It is NOT** a second Requirements/Architecture document, a TODO list, a test plan, an ADR store,
> or a collection of AI prompts. It never overrides Documentation; where it needs system truth to
> change, it escalates.
> **Status:** Assembled (Stage 13). **NOT yet declared READY** — Stage 14 (Plan Validation) and the
> Plan Readiness Gate remain.

## Authority hierarchy (governing this plan)

1. Approved **System Documentation**
2. Approved **Backend Service Documentation**
3. Approved **ADRs** (ADR-001..012)
4. **Implementation Plan** (this artifact)
5. Engineering Skills
6. AI Execution Guidance
7. Agent inference

The plan is downstream of layers 1–3. A conflict with any higher layer is an escalation, not a
silent plan change.

## Canonical model (frozen through Stage 12)

- **49 Work Units** = **36 READY · 11 SEAM-READY · 2 SPIKE · 0 BLOCKED**
- **9 decision/governance/documentation Nodes** (fenced; not implementation WUs)
- **Execution:** Foundation-first + Risk overlay → waves **W0 → W1 → W2 → W2.5(∥) → W3 → W4 → W5 → W6 → W7**
- **Gates:** G-SPIKE → G-FLOOR → **G-GUARD (critical)** → G-SEAM → G-IDENTITY → G-EDU → G-ASYNC → G-EXPERIENCE → G-CONTRACT

## Artifact set (Standard+ baseline)

| File | Purpose |
|------|---------|
| `implementation-plan.md` | Control document: definition, scope, strategy, state model, gates, how to read |
| `work-breakdown.md` | The 49 canonical Work Units (identity, outcome, state, boundary, deps, verification, fenced portion) |
| `dependencies.md` | Semantic typed dependency graph (BLOCK/CONTRACT/DATA/ENV/DECISION/EXTERNAL/VERIF) + floor/substrate model |
| `execution-sequence.md` | Strategy, waves W0–W7, exactly-once WU→wave map, gates |
| `verification.md` | Verification model (Outcome → AC → Method → Evidence) + regression-critical suite |
| `traceability.md` | Source → Obligation → WU → AC-seed → Verification matrix + coverage metrics |
| `risks.md` | Risk & uncertainty inventory (Stage 9), classifications, SPIKEs, impact |
| `decisions.md` | Resolved stack decisions (D2) + the 9 fenced Nodes + escalation record (ESC-01) |
| `ai-execution.md` | Guidance for the AI implementation agent: boundaries, escalation, completion/deviation protocol |
| `changes.md` | Change/deviation protocol + change log (ISSUE-08-01, lifecycle delta, 47→49 correction) |

## State model (exact meanings)

- **READY** — the complete implementation *and verification* outcome can be completed now.
- **SEAM-READY** — the architectural seam/contract can be implemented and consumed now; a
  mechanism-specific portion remains **fenced** for a later decision. Consumers may build on the seam.
- **SPIKE** — investigation is required before implementation commitment.
- **BLOCKED** — the WU boundary itself cannot be established without an unresolved decision. *(None in V1.)*

Fence annotations (do not change state): 🔧 mechanism · 🏭 vendor/infra · 📄 downstream-doc · 🚧 governance/ownership.

## How to read

Start with `implementation-plan.md` (control), then `execution-sequence.md` (what to build in what
order), consulting `work-breakdown.md` for each WU, `dependencies.md` for prerequisites, and
`verification.md` for how completion is proven. `decisions.md` + `risks.md` + `changes.md` govern the
open/fenced items and how reality-vs-plan divergence is handled. `ai-execution.md` is the operating
contract for an AI implementation agent.
