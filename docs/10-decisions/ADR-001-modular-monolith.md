# ADR-001 — Adopt Modular Monolith for V1

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
Madar V1 must satisfy, in priority order: strict tenant isolation & data correctness, fast-session responsiveness, speed-to-market/operational simplicity, AI cost/latency control, and (lowest) scalability headroom. The team is three senior engineers, possibly +1 AI. There is no V1 requirement for independent deployment or independent scaling of any domain area. Madar is a SaaS, but SaaS determines requirements (multi-tenancy, tenant isolation, customer-data boundaries, operational scalability) — it does not dictate an architectural style.

## Decision
Adopt a **Modular Monolith**: one primary deployable application, partitioned internally along the seven conceptual sub-domains, with strong internal boundaries and centralized tenant/authorization enforcement. Keep module boundaries clean so future extraction of a component remains possible if a concrete driver appears.

## Alternatives considered
- **Layered monolith** — rejected: does not structurally protect the domain boundaries established during Domain.
- **Microservices** — rejected for V1: serve only the lowest-ranked driver (scalability) while working against the highest (distributed isolation is harder to guarantee) and against operational simplicity at this team size. May become appropriate later if concrete drivers emerge (independent deployment, independently scaling workloads, multiple teams, stronger failure isolation).

## Consequences
- One thing to operate; boundaries preserved; isolation centralizable.
- Requires discipline to keep module boundaries honest in code.
- This is an **intentional** V1 architecture, not a 'couldn't afford microservices' compromise. Extraction is possible later without being pursued now.
