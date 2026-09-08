# Cross-Cutting — Security & Authorization

> **Authority:** **Normative** (authz model + security posture).
> **Source of truth** for the authorization model, authentication/claim posture, and minors'-data
> security principles.
> **Depends on:** ADR-004, ADR-008, ADR-010; `03-domain/invariants.md`.

## Authorization model (composite)

Every authorization decision combines **authenticated actor + role + authorized Teacher-Environment
context + relationship/ownership scope**. **Role alone is never sufficient**; tenant and relationship
checks are mandatory (ADR-010). This is the complete V1 model — no finer-grained permission matrix.

| Actor | Access |
|-------|--------|
| **Teacher** | Only within their authorized environment and its records |
| **Student** | Within **one active** authorized environment; only their own Enrollment's records |
| **Content Maintainer** | The central content/KB surface only; **no** access to teacher educational records |

## Tenant isolation (recap, canonical in Contracts/ADRs)

Tenant context is **server-derived** and never client-controlled (ADR-008); scope is enforced at both
the request/context boundary and the data-access boundary (ADR-004/007). This is the structural
guarantee behind INV-7.

## Authentication & claiming

**Teacher authentication (account holders).** A Teacher is a Madar **account holder** (a distinct
actor) who **authenticates** to access Madar. The Teacher account/authentication lifecycle — how a
prospective Teacher becomes an account holder and reaches the authenticated state that all capability
documents assume — is documented in [`../03-domain/actor-lifecycles.md`](../03-domain/actor-lifecycles.md).
The specific authentication mechanism (credentials, OTP, tokens, provider) is **not decided at the
system level** and is deferred to implementation, consistent with the claiming-mechanics deferral
below. This is a **separate path** from student entry and does not alter the student model.

**Student claiming (teacher-created identities)** — unchanged:

- Students are teacher-created; there is **no public student self-signup** in V1.
- A teacher-created Student may be **unclaimed** while records (attendance, recitation, payment, state,
  rating) are created against their Enrollment.
- The student later **claims** the existing global Student identity via **phone-based verification**,
  becoming an authenticating account. Claiming establishes access to the **existing** identity — it
  does not create a new identity or rebuild/migrate records.
- OTP/SMS provider and token mechanics are deferred to implementation/Operations (a claiming/auth
  concern, not the notification-channel decision).

## Minors' / student-data posture (principle-level)

- **Encryption in transit is mandatory.**
- Student data is accessible only through authenticated, authorized, tenant/relationship-scoped paths.
- **Teacher Private Notes remain teacher-only.**
- **Parent contact** is teacher-scoped data and does **not** create access rights or an account.
- Student/minor data is treated as **sensitive**, but V1 does **not** assert a specific regulatory
  regime without an established requirement.

> Retention, deletion, legal basis, and formal privacy/compliance requirements are **deferred to
> Operations** (`09-operations/`, `06-data/lifecycle-retention.md`). None is invented here.
