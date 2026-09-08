# Operations — Backup, Recovery & Retention Follow-up

> **Authority:** Normative (V1 backup/recovery stance).
> **Depends on:** `06-data/lifecycle-retention.md`.

## Backup & recovery (V1)

- V1 relies on the selected managed datastore's **automated backups and point-in-time recovery**
  where the managed service provides it.
- Backup/recovery capability **must be enabled** as part of production setup, and the recovery
  procedure **should be practically verifiable**.
- **No numeric RPO/RTO targets** are defined in V1 without an actual business requirement (avoid false
  precision).
- No custom backup cluster or bespoke disaster-recovery infrastructure is required for V1.

## Retention & privacy (Operations follow-up)

Per `06-data/lifecycle-retention.md`, V1 **retains prior-year data indefinitely** with **no deletion
workflow** — an explicit V1 scope decision, not a permanent policy.

The following remain an **Operations follow-up** and must be established before being treated as
binding: retention periods, deletion/erasure workflows, minor-data handling policy, legal basis, and
any formal privacy/compliance or data-residency requirements. **No specific regulatory regime is
asserted or invented at this stage.**
