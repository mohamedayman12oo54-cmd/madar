# AI Execution Guidance

> **Authority:** Layer 6 (AI Execution Guidance) — below the Documentation, ADRs, Implementation Plan, and
> Engineering Skills. This file gives an AI implementation agent the *execution context* for this plan.
> It is **not** a prompt library and does **not** restate the Engineering Skills System (which defines *how*
> engineering work is performed). It defines *what to respect* while executing the WUs.

## Operating authority

Obey this order on any conflict: **System Docs → Backend Service Docs → ADRs → this Implementation Plan →
Engineering Skills → this guidance → your own inference.** Never let a lower layer override a higher one, and
never convert an implementation discovery into new system truth.

## Documentation is truth; the plan is derived

Read the authoritative documentation for each WU before implementing it (sources are in `work-breakdown.md`
and `traceability.md`). If the plan and the documentation disagree, the documentation wins and the
discrepancy is a **deviation** to record (see `changes.md`), not a silent fix.

## Repository & boundary expectations

- One deployable, two runtime roles (web + worker) on a shared codebase/domain/persistence (D2-1).
- Seven private modules (BND-1): a module never reaches into another module's persistence; cross-module needs
  go through internal capabilities (e.g., IE-04).
- Isolation is enforced centrally at the data-access boundary (D2-2); never hand-roll per-query tenant
  filtering as the primary control, and never bypass the boundary.
- The worker reconstructs trusted context from server-created persisted state only (EX-1/FND-09); never trust
  client-derived context on the worker.
- Learning & AI is the **only** module that crosses the LLM seam (ADR-002/AI-01).

## Critical constraints (do not violate)

- Tenant context is **server-derived**; a client-supplied tenant is always refused (ADR-008).
- Every authorization is composite (actor + role + authorized env + relationship/ownership); role alone is
  never sufficient (ADR-010).
- Invariants INV-1..8 are enforced on **all paths**; a violation is rejected as business-rule/conflict, never
  partially applied or silently corrected (BR-1).
- The Fast-Session sync path performs no delivery/AI/batch work; event hand-off is atomic with the record
  (BR-2, ADR-005).
- AI is advisory and non-authoritative; a failed AI operation yields no partial product-state and never
  corrupts or blocks deterministic data (ADR-006).
- Teacher commercial access (trial/subscription) is distinct from student fee tracking; never conflate them.

## Dangerous assumptions to avoid

- Do **not** assume a Teacher account/authentication mechanism, an Environment provisioning **trigger**
  (cardinality itself is resolved — ADR-013/INV-9, no longer a fenced Node), a Teacher→Student
  invitation mechanism, the exact numeric/behavioral billing-policy sub-decisions (retry/grace numbers,
  refunds, proration), an OTP provider, an AI-persistence owner, a serialized API schema, or any vendor.
  All are fenced Nodes (`decisions.md`).
- Do **not** introduce `default-open` or any access policy for TAL-04; implement only the abstract
  access-state input seam.
- Do **not** redesign or duplicate the Student identity/claiming model; TAL-03 connects into it unchanged.

## Areas requiring explicit verification

Isolation (cross-tenant negative suites), invariant enforcement, atomic record+event hand-off (crash/replay),
async spine failure paths, Fast-Session sync-path purity, and the regression suite that proves the
Teacher-lifecycle additions changed nothing existing. See `verification.md`.

## Escalation conditions (STOP and ask)

Stop and escalate when a decision would materially change architecture, system contracts, domain invariants,
the security or tenant-isolation model, data ownership, external interfaces, a major technology choice,
documented behavior, scope, or a significant execution-strategy element — or when documentation is ambiguous
in a way that materially affects the outcome, or when resolving a fenced Node would touch an authoritative
boundary. Normal implementation decisions within an established WU boundary do not require escalation.

## Completion protocol (per WU)

A WU is complete only when its documented outcome is **verified** (not merely coded): acceptance criteria met,
verification method executed, evidence captured (`verification.md`). For SEAM-READY WUs, "complete" means the
**seam** is implemented and verified; the fenced mechanism portion stays explicitly deferred and is not
marked done. **Implemented ≠ Verified.**

## Deviation protocol

On any reality-vs-plan divergence (undocumented infrastructure, conflicting assumption, changed external
behavior, unexpected constraint, missing capability, new dependency): record the deviation, run impact
analysis, and route the decision (WU change / dependency change / verification change / documentation update /
ADR / replanning). Never silently rewrite the plan or the code around it. See `changes.md`.

## Required evidence

Per WU: test results (unit/integration/contract/negative as applicable), CI result, and a review record; for
SPIKEs, a spike report; for ops WUs, an ops record. Evidence is the difference between IMPLEMENTED and VERIFIED.
