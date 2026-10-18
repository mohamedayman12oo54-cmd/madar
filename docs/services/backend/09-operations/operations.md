# Backend Operations

> **Authority:** **Normative** for the guarantee-parity principle below; **References** the inherited
> deployment/backup/retention shape (canonical upstream).
> **Specializes:** `../../../09-operations/deployment.md`, `../../../09-operations/backup-recovery.md`,
> `../../../09-operations/knowledge-base.md`, `../../../10-decisions/ADR-001-modular-monolith.md`,
> `../../../10-decisions/ADR-012-web-worker-split.md`.
> **Design-first note:** no vendor, infrastructure mechanism, secret-management technology, OTP
> provider, RPO/RTO target, or new operational subsystem is invented here.

Backend Operations is primarily **confirm-and-route**, with **one** principle elevated for clarity.

## Confirm — the inherited operational shape applies to the Backend

- **Three environments:** development, staging, production. No additional preview environments in V1.
- **One codebase / one deployable**, running in **two runtime roles** (`ADR-001`, `ADR-012`):
  - **Web / API process** — synchronous requests and the latency-sensitive Fast Session.
  - **Worker process** — asynchronous jobs: notification dispatch, AI operations, any KB publish/index
    job.
  - The Worker is **not** a separate service or microservice — same application, modules, domain model,
    and persistence, in a different runtime role. **Each environment runs both roles.**
- **Hosting:** cloud-hosted, managed services wherever practical; **no specific cloud/vendor selected**
  (deferred).
- **Backup & recovery:** rely on the selected managed datastore's automated backups + point-in-time
  recovery; capability must be enabled in production and practically verifiable; **no numeric RPO/RTO**
  without an actual business requirement; no custom backup/DR infrastructure required for V1.
- **Retention:** V1 **retains prior-year data indefinitely** with **no deletion workflow** — an explicit
  V1 scope decision, not a permanent policy.
- **KB lifecycle:** draft → published/versioned; only published content is authoritative for AI
  consumption; publish/index processing may run as a **background job on the Worker** (`ADR-012`).

> Earlier architectural/runtime guarantees (Web/Worker separation, deterministic synchronous behavior,
> async isolation) remain **architecture/runtime behavior** and are **not** restated here as new
> operational policies merely for completeness.

## OP-PARITY — Guarantee-parity across environments and runtime roles

The Backend's established **security and correctness guarantees must hold across all three
environments and both runtime roles**. No environment or runtime role may intentionally weaken those
guarantees for operational convenience. This includes, as applicable:

- server-derived trusted execution context;
- tenant/environment isolation;
- composite authorization;
- relationship/ownership enforcement;
- non-bypassable invariant enforcement.

- The **Worker** does not receive a weaker trust, tenant-isolation, authorization, or
  invariant-enforcement model merely because it executes asynchronously. Its trusted context is
  reconstructed from server-created operation/job state (`../04-architecture/execution-model.md`, EX-1).
  This applies equally to any future Billing renewal/reconciliation job
  (`../../../10-decisions/ADR-014-billing-bounded-module.md`): it gets the same tenant/trust/integrity
  guarantees as the synchronous Web paths, never weaker ones because it runs on the Worker role.
- **Development and staging** do not imply relaxed isolation semantics merely because they are
  non-production.

> **Fence.** This is an **operational specialization** of existing cross-cutting and architectural
> guarantees, not a new security architecture or deployment-topology constraint. **"Parity" refers to
> the security and correctness guarantees — not** to identical infrastructure sizing, deployment
> configuration, scaling characteristics, or other operational implementation details, which remain
> Open and may legitimately differ by environment or runtime role.

## Routed Operations follow-ups (recorded, not resolved)

These are explicitly deferred to the Operations stage and are **not** resolved here:

- concrete cloud/hosting selection;
- concrete secret storage, injection, configuration-delivery, and rotation mechanisms
  (`../08-cross-cutting/configuration-secrets.md`);
- OTP / identity-verification provider mechanics;
- concrete backup verification procedures;
- numeric RPO/RTO — only if a later business requirement establishes the need;
- retention/deletion/privacy/legal operational policy where still explicitly deferred
  (`../../../06-data/lifecycle-retention.md`, `../08-cross-cutting/security-authz.md`);
- **concrete production scheduling and monitoring for any Billing renewal/reconciliation job** — the
  existing `--loop`-mode management-command mechanism (`process_ai_operations.py`,
  `process_notifications.py`) is a plausible template, but no concrete scheduler (cron/systemd timer/
  managed scheduler) is deployed anywhere in this repository today for *any* job, and none is decided
  here for Billing specifically (`../../../01-product/commercial-model.md` §Open items);
- **Kashier go-live/production-activation verification** (merchant activation, live webhook
  configuration, smoke-testing) — external, operational, not performed here
  (`../../../01-product/commercial-model.md` §External verification context).

See the consolidated list in `../11-validation/open-items.md`.
