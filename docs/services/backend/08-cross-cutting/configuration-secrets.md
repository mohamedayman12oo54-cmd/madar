# Cross-Cutting — Configuration & Secret Handling (Backend)

> **Authority:** **Normative** at the **principle level** (a Backend cross-cutting rule: *what must be
> true*). The operational *how* is deferred to Operations.
> **Depends on:** `security-authz.md`, `../00-overview/backend-overview.md` (the provider neighbor set).
> **Design-first note:** this selects **no** configuration or secret-management technology. No vendor,
> secret manager, hosting mechanism, environment-variable strategy, or deployment technology is
> implied.

The Backend integrates the three Madar-owned external providers (LLM, Push, Video) and depends on a
deferred OTP/Identity-Verification mechanism — all with credentials and endpoints, all vendor-Open.
This makes provider configuration and secret handling a **Backend cross-cutting concern at the
principle level**.

## The principles (technology-independent)

- Provider **credentials/secrets must never be hard-coded** into source code.
- Credentials/secrets **must not be exposed** through application logs, error telemetry, or other
  observability output (consistent with the sensitive-data logging restriction in `observability.md`).
- Provider configuration remains **behind the established Madar-owned external integration boundaries**
  (`../../../07-contracts/external-interfaces.md`), rather than being exposed as arbitrary configuration
  to domain modules.
- These principles apply consistently to the established external providers **and** to any
  future/deferred provider mechanism that enters the Backend boundary (including the OTP/Identity-
  Verification mechanism).

## What is deferred to Operations (the *how*)

- concrete secret storage mechanism;
- secret injection mechanism;
- configuration delivery mechanism;
- secret rotation/lifecycle procedures;
- operational access controls and deployment-specific management.

Cross-Cutting establishes **what must be true**; Operations (`../09-operations/operations.md`) will
establish **how it is securely managed and operated**.
