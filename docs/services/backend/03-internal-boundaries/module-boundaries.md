# Internal Module Boundaries

> **Authority:** **Normative** for the Backend's internal boundary rules.
> **Specializes:** `../../../03-domain/domain-model.md`, `../../../03-domain/invariants.md`,
> `../../../04-architecture/building-blocks.md`.
> **Scope note:** the System domain model, entities, ownership, invariants, lifecycles, two-level
> scoping, and Grade-derived monthly context are **authoritative and are not re-modeled here**. This
> document only fixes the Backend's internal ownership and collaboration boundaries needed to enforce
> that established domain correctly.

## The key internal invariant

> Cross-module collaboration occurs through explicit module capabilities; cross-module direct
> persistence access is prohibited; cross-cutting guarantees apply across every applicable execution
> path.

## BND-1 — Private module persistence; capability-oriented collaboration

A Backend module **must not** directly read, write, or depend on another module's owned persistence
representation (tables, repositories, or equivalent storage details) — **even though all modules
reside in the same database and the same deployable application**. Sharing a database does **not**
imply sharing persistence ownership.

When one module needs information owned by another module, it obtains that information through an
**explicit internal capability** exposed by the authoritative module. For example, if Financials needs
Enrollment/Grade information to resolve a fee, it depends on an Identity & Enrollment internal
capability rather than reading Enrollment/Grade persistence directly.

- The rule is **capability-oriented**, not generic entity/CRUD access across modules.
- This is an **in-process modular boundary**, not a network or microservice boundary — consistent with
  the one-deployable Modular Monolith (`../../../10-decisions/ADR-001-modular-monolith.md`,
  `../../../10-decisions/ADR-012-web-worker-split.md`).
- Exact interface shapes and mechanisms are Architecture/implementation concerns
  (`../07-contracts/internal-contracts.md`).

## BND-2 — Cross-cutting enforcement vs. per-module ownership authorization

Tenant/context/isolation enforcement is a **Backend-level cross-cutting concern**, not the
responsibility of any single domain module. The Backend provides, around/beneath the domain modules:

- establishing authenticated actor context;
- establishing and propagating the server-derived tenant/environment context
  (`../../../10-decisions/ADR-008-server-derived-tenant-context.md`);
- enforcing tenant/environment isolation at the request and data-access boundaries
  (`../../../10-decisions/ADR-004-two-layer-tenant-isolation.md`,
  `../../../10-decisions/ADR-007-two-level-data-scoping.md`);
- the common authorization infrastructure required by the composite authorization model.

This does **not** centralize all authorization into one generic module. The composite model remains
**authenticated actor + role + authorized tenant/environment + relationship/ownership**
(`../../../10-decisions/ADR-010-composite-authorization.md`), where:

- the **structural** guarantees (context + isolation) are cross-cutting, and
- the **resource-specific** relationship/ownership checks live with the owning module, where those
  rules are intrinsic to the resource being accessed.

No module may independently weaken, redefine, or bypass the system-level tenant-isolation model.
Concrete middleware/policy/repository/ORM mechanisms remain Open.

## BND-3 — Notification event ownership at the seam

The domain module that owns the triggering domain fact owns the **event semantics and event
emission**; **Notifications** owns **consumption and dispatch**.

For example, when Educational Operations records an attendance outcome requiring an "Absent"
notification:

1. Educational Operations owns the domain transition/fact.
2. Educational Operations creates the corresponding notification event.
3. The domain record and a **durable event hand-off** are committed **atomically** within the emitting
   module's own transactional boundary
   (`../../../10-decisions/ADR-005-async-notification-dispatch.md`).
4. Notifications consumes the resulting hand-off asynchronously.
5. Notifications owns delivery orchestration, retry/dispatch behavior, and Push-interface integration.

Notifications does **not** independently infer or recreate domain facts from other modules' data, and
does **not** write into or own the emitting module's persistence (consistent with BND-1). The
established five-event catalog remains System-level truth; this fixes ownership only at the internal
module seam. The transactional hand-off pattern is detailed in
`../04-architecture/architecture.md` and `../05-runtime/fast-session.md`.

## BND-4 — Billing module boundary (added after the commercial-design pass)

**Billing** (`../../../10-decisions/ADR-014-billing-bounded-module.md`) is an eighth internal module,
following the same rules as BND-1/BND-2 above: it owns its private persistence (DAT-5,
`../06-data/data-model.md`) and exposes explicit internal capabilities for other modules that need to
know, e.g., whether a given Teacher Environment currently has access. No other module reads Billing's
persistence directly, and Billing does not read another module's persistence directly — it obtains
Environment/Enrollment context it needs (e.g., which Environment a Subscription belongs to) through
the Identity & Enrollment module's capability, the same as Financials already does for fee resolution.

Billing's **inbound webhook responsibility** (`../../../10-decisions/ADR-016-inbound-webhook-exception.md`)
and its **payment-provider interface** (`../../../10-decisions/ADR-015-payment-provider-interface.md`)
are owned entirely within the Billing module boundary — no other module is a secondary webhook
recipient or payment-provider caller.

## Consistency with the all-paths guarantee

BND-2 (cross-cutting isolation beneath the modules) and BR-1 (all-paths invariant enforcement,
`../02-requirements/backend-requirements.md`) reinforce each other: both push enforcement below the
point where any single module could forget it. How this holds on the Worker path as well as the Web
path is defined in `../04-architecture/execution-model.md`.
