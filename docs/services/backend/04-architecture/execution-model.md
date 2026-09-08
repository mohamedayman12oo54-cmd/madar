# Backend Execution Model — Web / Worker

> **Authority:** **Normative** for the Backend execution rules below.
> **Specializes:** `../../../10-decisions/ADR-012-web-worker-split.md`,
> `../../../10-decisions/ADR-006-ai-async-failure-tolerant.md`,
> `../../../10-decisions/ADR-011-selective-idempotency.md`, `../../../02-requirements/quality.md`.
> **Design-first note:** the concrete mechanism for serializing, transporting, storing, or
> reconstructing execution context — and the concrete async mechanism (queue/job technology) — remain
> **Open** implementation/runtime concerns and are not prescribed here.

## Two runtime roles over one structure

The Backend runs in two runtime roles sharing the same codebase, modules, domain model, and
persistence (`../../../10-decisions/ADR-012-web-worker-split.md`):

- **Web / API process** — synchronous requests and the latency-sensitive Fast Session.
- **Worker process** — asynchronous jobs: notification dispatch, AI operations, and any KB
  publish/index job.

The Worker is **not** a separate service or microservice — it is the same application in a different
runtime role. Both roles execute against the same module boundaries, domain responsibilities, and
persistence ownership (`architecture.md`).

## EX-1 — Trusted execution context across Web and Worker

> Any worker execution that can access or mutate tenant/environment-scoped data must execute within an
> explicitly established, **trusted execution context** reconstructed from server-created
> operation/job context.

**Web path:**

1. Authenticate the actor.
2. Establish the authorized, **server-derived** tenant/environment context
   (`../../../10-decisions/ADR-008-server-derived-tenant-context.md`).
3. Perform the applicable authorization, isolation, and invariant checks.
4. If asynchronous execution is required, create the trusted operation/job context on the server side.

**Worker path:**

1. Receive the server-created operation/job context.
2. **Re-establish** the applicable execution context before accessing or mutating scoped data.
3. Execute through the **same module capabilities** and under the **same** applicable isolation,
   authorization, and invariant guarantees.
4. **Never** derive tenant/environment scope from client-supplied values.
5. **Never** operate as an unscoped privileged process in order to bypass module or isolation
   boundaries.

This does **not** require every worker job to carry an identical full actor context. The execution
context contains the **trusted scope and identity appropriate to the operation**. In particular, any
worker execution touching tenant/environment-scoped data must have an explicitly established trusted
scope.

This is what makes the guarantees hold on the async paths: `teacher_environment_id` is always
server-derived; tenant isolation is non-bypassable across applicable execution paths (BND-2); and
invariant enforcement applies to every write path (BR-1).

## EX-2 — Common async principles; Operation and Job remain distinct

The Backend asserts a **common model for asynchronous execution** — its applicable principles are:
trusted execution context (EX-1); lifecycle/state handling where externally meaningful; failure
semantics where externally meaningful; idempotency where required
(`../../../10-decisions/ADR-011-selective-idempotency.md`); retry behavior where applicable;
observability; and enforcement of the same applicable isolation/invariant guarantees as other
execution paths.

Under that common model, **externally-meaningful Operations and internal Worker Jobs remain
structurally distinct**:

- **Externally-meaningful Operations** expose an observable lifecycle and result/failure semantics
  appropriate to their consumers. The three AI operations follow the established
  `Submitted → Processing → Succeeded | Failed` lifecycle. KB publish/processing has an observable
  outcome/failure where it affects AI-readiness and is Content-Maintainer-facing.
- **Internal Worker Jobs** (e.g., notification dispatch) remain internal execution units and do not
  become client-facing Operations merely because they run asynchronously.

There is **no** single universal runtime abstraction for all asynchronous work. The concrete
implementation mechanism is Open.

> **Escalation trigger.** If a future choice to make a particular operation client-facing would alter
> an established API surface or system-level contract, that change must be **escalated** rather than
> inferred from this model (`../README.md`).

## EX-3 — Lifecycle & access-state carry to the Worker (no new worker behavior)

The upstream lifecycle correction (Teacher authentication, Environment establishment, access state)
does **not** introduce new worker mechanics; it only clarifies that the **trusted context** a worker
reconstructs (EX-1) is the *same* server-established Teacher/Environment context, now with an explicit
origin. Two bounded consequences:

- A worker job initiated by a Teacher operation continues to execute under the **reconstructed trusted
  context** — the same server-derived Teacher/Environment scope, never client-derived or
  unscoped-privileged. Teacher authentication happens at the **web boundary** where the operation is
  submitted; the worker does not re-authenticate, it reconstructs the already-established trusted
  context (`../01-scope/teacher-access-lifecycle.md`, TAL-1/2).
- **Where** an access-state check applies (TAL-5) is an access-decision-boundary question, not a new
  worker capability. Whether access is re-evaluated for asynchronous work, and the exact behavior if
  access changes between submission and execution, depend on the **fenced** access-not-granted behavior
  and are **not decided here**. The Backend introduces no new worker behavior merely because the
  lifecycle now exists.

## Consistency notes

- The canonical end-to-end async-operation runtime path is in `../05-runtime/async-operations.md`.
- Teacher/Environment lifecycle and access-state responsibilities are in
  `../01-scope/teacher-access-lifecycle.md`.
- The Fast-Session minimal synchronous path and its atomic event hand-off are in
  `../05-runtime/fast-session.md`.
- Guarantee-parity of these rules across all environments and both runtime roles is stated in
  `../09-operations/operations.md`.
