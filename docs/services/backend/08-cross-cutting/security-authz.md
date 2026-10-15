# Cross-Cutting — Security & Authorization (Backend)

> **Authority:** **Normative** for the Backend enforcement split below; **References** the inherited
> composite model and security posture (canonical upstream).
> **Specializes:** `../../../08-cross-cutting/security-authz.md`,
> `../../../10-decisions/ADR-004-two-layer-tenant-isolation.md`,
> `../../../10-decisions/ADR-008-server-derived-tenant-context.md`,
> `../../../10-decisions/ADR-010-composite-authorization.md`.

The composite authorization model and the security/privacy posture are **binding and inherited**. This
document specializes only *where enforcement lives* within the Backend.

## The enforcement split

- **Structural guarantees are cross-cutting.** Authenticated-actor context, server-derived
  tenant/environment context establishment + propagation, request- and data-access-boundary isolation
  enforcement, and the common authorization infrastructure sit **around/beneath** the domain modules
  (`../03-internal-boundaries/module-boundaries.md`, BND-2). No module implements its own isolation;
  no module may weaken, redefine, or bypass the system tenant-isolation model.
- **Resource-specific authorization is per-module.** Relationship/ownership checks intrinsic to a
  resource live with the module that owns the resource.

Together these realize the inherited composite decision — **actor + role + authorized tenant/environment
+ relationship/ownership**, role alone never sufficient (`ADR-010`) — without centralizing all
authorization into one generic module.

**Access state is a separate, prior question, now owned by the Billing module.** The commercial-design
pass (`../../../01-product/commercial-model.md`) and
`../../../10-decisions/ADR-018-billing-entitlement-boundary.md` make concrete what TAL-5 named
abstractly: the **Billing** module (`../../../10-decisions/ADR-014-billing-bounded-module.md`) owns the
commercial decision of what a Teacher's current Subscription/Trial state permits, and exposes it as an
explicit **entitlement-policy contract** — a capability other boundaries consult, not a side effect of
any other mechanism. This sits **alongside, and after**, not inside, the composite authorization
model: composite authz (this document, `ADR-010`) governs **what** an authenticated, authorized
Teacher may do; entitlement governs **whether access is currently granted at all** and which
plan-gated capabilities are available.

> **Explicit caution — do not fold entitlement into the authentication hook.**
> `accounts/authentication.py`'s `MadarJWTAuthentication.get_user()` is the one per-request hook every
> authenticated request already passes through, and it already re-checks session revocation and (for
> students) active-enrollment status on every request. It would be a natural-looking shortcut to add
> entitlement/billing checks there too, merely because the hook is available on every request — **this
> is explicitly rejected** (`ADR-018`). Entitlement is a commercial-policy decision with different
> ownership (Billing, not identity/auth) and a different change cadence (plan rules, not session
> mechanics); it must be consulted at the correct authorization/application boundary, **after** an
> authenticated actor and authorized tenant/environment context are already resolved — not bolted onto
> the authentication hook.

Frontend-hiding of gated capabilities is explicitly **insufficient** — entitlement must be enforced at
the Backend. During an access-not-granted state, the entitlement contract must still permit
authentication, billing-resolution actions, and data review/export
(`../../../01-product/commercial-model.md` §Access-not-granted principle). The exact student-facing
restricted-access behavior and the complete teacher read-only ruleset remain **fenced** — see
`../01-scope/teacher-access-lifecycle.md` (TAL-5) and `../../../01-product/commercial-model.md` §Open
items.

## Non-bypassability (recap)

Tenant context is server-derived and never client-controlled (`ADR-008`); scope is enforced at both
the request/context boundary and the data-access boundary (`ADR-004`/`ADR-007`). This is the
structural guarantee behind INV-7. Invariant enforcement is a hard, all-paths guarantee
(`../02-requirements/backend-requirements.md`, BR-1). These guarantees hold on the **Worker** path as
well as the **Web** path, via reconstructed trusted context
(`../04-architecture/execution-model.md`, EX-1), and with equal strength across all environments and
runtime roles (`../09-operations/operations.md`).

## Authentication & claiming (inherited posture)

**Teacher authentication (account holders).** A Teacher is a Madar **account holder** — a distinct,
authenticatable actor — who **authenticates** to reach the "authenticated actor" state the composite
model and all capability documents assume. This is a **separate path** from student entry and does
**not** alter the student model. The System Documentation does **not** select the Teacher
authentication mechanism (credentials / OTP / tokens / provider); the Backend names the responsibility
and contract boundary but does not invent the mechanism. The Backend-level Teacher account/auth
responsibility and its fenced mechanism are documented in
`../01-scope/teacher-access-lifecycle.md` (TAL-1), specializing
`../../../03-domain/actor-lifecycles.md` and the Teacher-authentication note in
`../../../08-cross-cutting/security-authz.md`.

**Student claiming (teacher-created identities) — unchanged:**

- Students are teacher-created; there is **no public student self-signup** in V1.
- A teacher-created Student may be **unclaimed** while records are created against their Enrollment.
- The student later **claims** the existing global identity via **phone-based verification**, becoming
  an authenticating account. Claiming establishes access to the **existing** identity — it does not
  create a new identity or rebuild records.
- The claiming flow depends on an **OTP / Identity-Verification mechanism** whose form is **deferred**
  and **must not** be conflated with the Push notification provider
  (`../00-overview/backend-overview.md`, neighbor set). OTP/token mechanics are an implementation/
  Operations concern.

## Minors' / student-data posture (inherited, principle-level)

- **Encryption in transit is mandatory.**
- Student data is accessible only through authenticated, authorized, tenant/relationship-scoped paths.
- **Teacher Private Notes remain teacher-only** and are never visible to the student.
- **Parent contact** is teacher-scoped data and grants **no** access rights or account.
- Student/minor data is **sensitive**, but V1 asserts **no specific regulatory regime** without an
  established requirement — and none is invented here.

> Retention, deletion, legal basis, and formal privacy/compliance requirements are **deferred to
> Operations** (`../09-operations/operations.md`, `../../../06-data/lifecycle-retention.md`). None is
> invented here.
