# Validation — Traceability (Backend)

> **Authority:** Descriptive (documentation quality control, not system knowledge).
> **Specializes:** `../../../11-validation/traceability.md`, `../../../11-validation/consistency-audit.md`.
> **Purpose:** show that the Backend specialization traces coherently from inherited system truth to
> Backend-level behavior, with no contradiction and no silent narrowing of inherited capability.

## Coherence chains (inherited → Backend)

### Isolation chain

```
Server-derived tenant context (ADR-008)
  → teacher_environment_id as a uniform structural isolation attribute, ≠ shared ownership (BD-16 / DAT-1)
  → cross-cutting isolation enforcement beneath private modules (BD-9 / BND-2)
  → holds on the Worker via reconstructed trusted context (BD-12 / EX-1)
  → guarantee-parity across environments and runtime roles (BD-20 / OP-PARITY)
```
One coherent thread; no divergence.

### Fast-Session chain

```
Minimal per-tap synchronous transaction (BD-6 / BR-2)
  → atomic domain-write + durable event hand-off owned by the emitting module (BD-10 / BND-3, ADR-005)
  → asynchronous dispatch as an internal Worker Job (BD-7 / BD-13)
  → Web/Worker runtime separation (ADR-012)
```

### AI chain

```
AI as a non-exceptional internal module (BD-14)
  → canonical async-operation spine, Quiz & State-recommendation only (BD-15)
  → Backend↔AI internal capability contract, specify-to-seam (BD-17)
  → semantic failure mapping, wire-level deferred (BD-18)
  → AI product-state persisted; LLM never source of truth; persistence ownership Open (DAT-3)
```
Consistent; the Study Assistant interaction model is openly deferred, not fabricated.

## No silent narrowing of inherited capability

No Backend decision narrows or contradicts an inherited System capability. Each Backend-level decision
either **specializes** established System knowledge or **fills a genuine service-level gap** the system
explicitly left open. The two design tensions surfaced during discovery were resolved without
softening a boundary:

| Tension | Resolution |
|---------|------------|
| Cross-cutting data-access enforcement vs. per-module persistence privacy | Reconciled: a shared enforcement control every module's own data access passes through (BD-9 / BD-16); no module owns another's isolation. |
| ADR-005 atomicity vs. per-module persistence privacy (event hand-off) | Reconciled: the emitting module owns the atomic domain-write + durable event hand-off within its own boundary; Notifications consumes (BD-10). |

## One recorded self-correction

An earlier working shorthand attributed specific AI-related persistence (quizzes/answers/scores/advisory
recommendations) as AI-Module-owned. This was corrected: those AI outputs are **persisted as Madar
product state**, but **which module owns that persistence is Open** and is not back-inferred from the
data being AI-related (DAT-3). Recorded here so the correction is traceable, not silent.

## Lifecycle-alignment pass (upstream Teacher/commercial lifecycle → Backend)

The System Documentation's lifecycle-correction pass (new `03-domain/actor-lifecycles.md`,
`01-product/access-lifecycle.md`; existence-notes in `system-overview.md`, `glossary.md`,
`08-cross-cutting/security-authz.md`; new deferred items in `rejected-deferred.md`) propagated
downstream additively. Mapping from System lifecycle concept → Backend home:

| System-level concept | Backend responsibility/home | Class |
|----------------------|-----------------------------|-------|
| Teacher account holder + authentication | `01-scope/teacher-access-lifecycle.md` (TAL-1); `08-cross-cutting/security-authz.md` | Newly required (mechanism fenced) |
| Teacher Environment establishment + empty initial state | `01-scope/teacher-access-lifecycle.md` (TAL-2); `06-data/data-model.md` (DAT-4) | Newly required (trigger/cardinality fenced) |
| Empty → usable (initial use) | `01-scope/teacher-access-lifecycle.md` (TAL-3) | Contextually affected (framing only) |
| Teacher → Student introduction | `01-scope/teacher-access-lifecycle.md` (TAL-4) | Newly required (connection only; claiming model unchanged) |
| Free Trial → Subscription access state | `01-scope/teacher-access-lifecycle.md` (TAL-5); `08-cross-cutting/security-authz.md`; `07-contracts/external-api-alignment.md` (AL-2); `06-data/data-model.md` (DAT-4) | Newly required (abstract boundary; commercial mechanics fenced) |
| Contract preconditions (auth precedes; environment availability; access gating) | `07-contracts/external-api-alignment.md` (AL-2) | Contextually affected |
| Worker context under the lifecycle | `04-architecture/execution-model.md` (EX-3) | Contextually affected (no new worker behavior) |

**No contradiction introduced.** The Backend chain terminates exactly at the "authenticated Teacher
operating an established Environment" precondition the capability docs already assumed, and enters the
Student model exactly at its existing "teacher-created" origin. The Student identity/claiming
architecture, composite authorization, tenant isolation, all ADRs, and student fee tracking are
**preserved unchanged**.

## Validation principle carried into documentation

> Validation does not require every implementation or design detail to be resolved. It requires
> unresolved items to be correctly classified, explicitly owned/routed, consistent with established
> boundaries, and non-blocking for the documentation purpose at hand.

The open items are enumerated in `open-items.md`.
