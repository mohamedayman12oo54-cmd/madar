# Backend Requirements

> **Authority:** **Normative** (Backend behavioral guarantees). These **specialize** the established
> System functional requirements, quality priorities, invariants, and constraints into enforceable
> server-side behavior. They introduce no implementation-specific choice and no false precision.
> **Upstream:** `../../../02-requirements/functional.md`, `../../../02-requirements/quality.md`,
> `../../../03-domain/invariants.md`.

The System functional requirements, quality ranking, invariants, and constraints are **binding and
inherited**. This document does not restate them; it specializes them into Backend-level,
testable server-side behavior.

## BR-1 — Invariant enforcement is a hard, non-bypassable server guarantee

The hard, non-bypassable enforcement of domain invariants across every applicable mutation path is
**already-established normative knowledge** (`../../../03-domain/invariants.md`). This is the Backend
**specialization of how that established guarantee applies within the Backend boundary** — not a new
decision and not a strengthening of a system ADR.

- A request that would violate an applicable invariant or perform an illegal lifecycle/state
  transition **must be rejected** with the appropriate business-rule/conflict error under the uniform
  error semantics. It must never be partially accepted or silently corrected.
- Enforcement holds across **every** Backend write path that can mutate the affected state: **no**
  alternate endpoint, worker path, internal command, or retry path may bypass an applicable invariant.
- The Backend requirement is the **behavioral guarantee** — the invalid mutation is not accepted. The
  exact status-code mapping and serialized error schema are Contract-level concerns
  (`../07-contracts/external-api-alignment.md`).

Representative cases: a duplicate Enrollment for the same `Student × Teacher Environment × Academic
Year` (INV-2); a Group membership outside the Enrollment's Grade (INV-4); a write to a Session
Instance that is not Open (`../../../03-domain/lifecycles.md`); any operation that would leave persisted
state inconsistent with an established invariant.

Expected shape: `request → invariant check/enforcement → reject if violated` — never
`request → best-effort validation → potentially inconsistent state`.

## BR-2 — Fast-Session per-tap path is a minimal, independently-committed transaction

The System quality bar for the Fast Session is deliberately qualitative ("immediate, lightweight,
usable at 40–50 per group on a mid-range phone" — `../../../02-requirements/quality.md`). The Backend
requirement that supports it:

Each Fast-Session tap/mark is handled as an **independent, individually-committed write**. The
synchronous server-side work is limited to:

1. authenticate/authorize the request and establish the applicable context;
2. validate the requested state transition / business rules;
3. persist the domain record/change;
4. persist the corresponding notification event **atomically** with that change where a notification
   is required (Absent, Not-Studied);
5. return the result.

The synchronous request path **must not** perform notification delivery, AI execution, cross-student
batch processing, or other unrelated asynchronous work. Notification **dispatch** remains asynchronous
on the Worker (`../../../10-decisions/ADR-005-async-notification-dispatch.md`).

**No numeric Backend latency target** is established at the Requirements stage; introducing an
arbitrary server-side number here would be false precision. Concrete performance targets remain an
Architecture/Operations/implementation concern **if** later evidence or testing requires them.

## BR-3 — Asynchronous observability is tiered by externally-meaningful lifecycle

> **General rule.** Every asynchronous operation with an **externally meaningful lifecycle** must have
> observable state and explicit failure semantics **at the appropriate boundary**. Purely internal
> background work does not automatically require a client-facing operation contract, but it must still
> have sufficient internal observability for reliable operation and troubleshooting.

This resolves into three tiers, kept as distinct concepts:

| Async work | Observability requirement | Boundary |
|------------|---------------------------|----------|
| **AI operations** (Quiz, State-recommendation) | Full `Submitted → Processing → Succeeded \| Failed`, externally queryable, machine-readable failure | Client-facing API contract |
| **KB publish / processing** | Publish → processing (if required) → observable outcome → explicit failure state, **when** the outcome affects AI-readiness | Content-Maintainer-facing KB lifecycle |
| **Purely internal worker jobs** (e.g., notification dispatch) | Internal observability only (reliability / troubleshooting) | Not a public operation |

Notification dispatch is async but is **not** a client-observable operation — it is fired-and-forgotten
(`../../../10-decisions/ADR-005-async-notification-dispatch.md`), which fits the internal-job tier.

## Homework (fenced)

Homework upload/annotation is outside the V1 Definition-of-Done; no committed Backend requirement
depends on it (`../01-scope/responsibilities.md`).
