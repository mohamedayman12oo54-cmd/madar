# Risk & Uncertainty Model (Stage 9)

> **Authority:** Layer 4 (derived). Risk is overlaid on the WU + dependency model and affects the
> execution/verification model **only where justified**. Uncertainty is not converted into a blocking
> dependency, and fenced mechanisms are not turned into implementation tasks.

## Risk inventory & classification

| ID | Risk / uncertainty | Type | Severity | Source |
|---|---|---|---|---|
| R-01 | Isolation-enforcement mechanism (INV-7, driver #1) | Technical | High | SPIKE FND-03 |
| R-02 | Outbox / at-least-once / idempotent-consumer correctness | Technical | High | SPIKE FND-08 |
| R-03 | External LLM latency/failure (Quiz / State-rec) | External | Med | ADR-006; AI-02/03, RUN-02 |
| R-04 | Push / Video vendor undecided | External | Low-Med | NODE-Vendors; EXT-02/03 |
| R-05 | Teacher authentication mechanism undecided | Decision | Med | NODE-TeacherAuth; TAL-01 |
| R-06 | Environment cardinality (one vs many) — Open, structural-ish | Decision/Structural | Med-High | NODE-EnvProvision; TAL-02, DAT-4 |
| R-07 | Environment provisioning trigger undecided | Decision | Low-Med | NODE-EnvProvision; TAL-02 |
| R-08 | Access-not-granted behavior (suspend/grace/read-only) + retention — Open | Decision/Product | Med-High | NODE-AccessBehavior; TAL-04, EX-3 |
| R-09 | Teacher→Student invitation mechanism undecided | Decision | Low | NODE-Invitation; TAL-03 |
| R-10 | OTP/identity-verification (student claiming) | Decision | Med | NODE-OTP; AUTH-01 |
| R-11 | Wire-level API taxonomy/schema | Downstream-doc | Low | NODE-WireAPI; API-01 |
| R-12 | AI product-state persistence **ownership** | Boundary/Open | Med | NODE-AIOwnership; SE-04/AI-02/03 |

## Impact on the plan (only where justified)

- **R-01 / R-02 → decomposition, ordering, verification depth.** Justify SPIKEs (FND-03, FND-08) in **W0**,
  before consumers (FND-04, FND-09/10, RUN-01/02); raise verification depth (isolation negative-suites,
  Outbox crash/replay). No change to the WB.
- **R-06 (cardinality) → possible structural effect on the Teacher↔Environment association (DAT-4).**
  ADR-008 already permits plural "authorized environments," so it is **structurally non-blocking**; the
  per-Teacher limit is a product decision. **Classification: decision Node, not SPIKE, not a blocking
  dependency** — flagged as the most structurally sensitive delta item.
- **R-08 (access-not-granted) → enforcement semantics + possible worker re-evaluation (EX-3 fenced) +
  retention.** The **seam** (access-state input) is plannable; the **enforcement behavior** is fenced.
  **Classification: product/System decision.** A small SPIKE may be warranted *after* the product decision
  if the enforcement point proves complex — **not now**.
- **R-03/R-04/R-10/R-11/R-12 → unchanged** from the approved posture: fenced/deferred with seams ready.
- **R-05/R-07/R-09 → no decomposition impact;** isolated behind WS-TAL seams; decision Nodes only.

## SPIKE requirements

- **Existing (unchanged):** FND-03 (isolation), FND-08 (Outbox). **No new SPIKE is forced by the lifecycle delta.**
- **Watch (conditional, not now):** access-not-granted enforcement point (R-08) — becomes a SPIKE only if the
  product decision reveals enforcement/worker-reeval complexity.

## Ordering / readiness / gate implications

- **Ordering:** unchanged in substance; WS-TAL seams enter early (W2.5) with mechanisms deferred.
- **Readiness:** consumers stay READY on the seams; mechanism-completion of SEAM-READY WUs and AUTH-01 is
  gated on decision Nodes — this does **not** prevent starting execution, only declaring those WUs "done".
- **Gate:** the plan does not reach overall READY until R-05/06/08 (+ R-10) are resolved. These are
  **product/System-owned**, not planning blockers.

## Stage 9 gate

The model is uncertainty-aware; risks influenced verification depth and ordering where justified; no
over-blocking; fenced items remain fenced. **PASS.**
