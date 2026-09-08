# Data — Lifecycle & Retention

> **Authority:** Normative for the **V1 retention stance** (an explicit scope decision).
> **Depends on:** `03-domain/lifecycles.md`; `09-operations/`.

## Yearly boundary

Enrollments are scoped to an Academic Year and end with it; a new year creates **new** Enrollments for
continuing students (`03-domain/lifecycles.md`). Prior-year Enrollments and their records are retained
as historical, read-only context. Historical academic context is preserved via the Enrollment's
immutable Grade (INV-6); a new year never rewrites prior-year records.

## V1 retention stance (explicit)

- Prior-year data is **retained indefinitely** in V1.
- There is **no** user-facing or automated deletion workflow for students or teachers in V1.
- A student leaving a teacher does **not** trigger automatic deletion; an ended Academic Year does not
  trigger archival or purge.

> **This is an explicit V1 operational scope decision, not a permanent legal/privacy policy.** No
> specific retention period, minor-data deletion SLA, legal basis, or regulatory regime is asserted.
> Retention/deletion/erasure and formal privacy/compliance requirements are an **Operations
> follow-up** and must be established before being treated as binding (see
> `09-operations/backup-recovery.md` and `08-cross-cutting/security-authz.md`).
