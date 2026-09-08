# Madar — System Documentation

> **Authority:** Normative (navigation + source-of-truth map)
> **Scope:** System-level V1 documentation. This is the shared source of truth that all
> individual services/clients (Teacher web, Student mobile-web, Content-Maintainer tool,
> and any future Backend/Frontend/AI service documentation) must align with.
> **Status:** Complete `docs/` tree (System-level, V1). All twelve knowledge domains are written.
> The next phase is the service/client Zoom-In (Backend / Student-client / AI), each specializing
> this System model without redefining it.

Madar is a multi-teacher SaaS platform that gives an Egyptian private-tutoring teacher one
organized digital environment to run the administrative and educational side of their offline
teaching — replacing notebook + memory + WhatsApp + scattered tools.

---

## How this documentation is organized

Each folder is a **stable knowledge domain**. The number of files inside is adaptive: we write
what the stabilized system knowledge requires, and we mark negative space (things deliberately
*not* in V1) explicitly rather than omitting it.

| Folder | Knowledge domain | Written? |
|--------|------------------|----------|
| `00-overview/` | Orientation, glossary | ✅ |
| `01-product/` | Vision, scope, V1 boundary, access lifecycle | ✅ |
| `02-requirements/` | Functional + quality + constraints | ✅ |
| `03-domain/` | Domain model, invariants, lifecycles, actor lifecycles | ✅ |
| `04-architecture/` | Structure, modules, building blocks | ✅ |
| `05-runtime/` | Fast Session · State pipeline · AI Quiz | ✅ |
| `06-data/` | Data model, consistency, retention | ✅ |
| `07-contracts/` | API + external interfaces | ✅ |
| `08-cross-cutting/` | Security/authz, observability | ✅ |
| `09-operations/` | Deployment, KB lifecycle, backup | ✅ |
| `10-decisions/` | ADRs, rejected/deferred register | ✅ |
| `11-validation/` | Traceability, consistency audit | ✅ |
| `diagrams/` | Mermaid sources for all views | ✅ |

---

## Authority model

Documentation carries one of three authority levels. This distinction prevents a reader from
treating a description or a diagram as a binding contract.

- **Normative** — implementation MUST comply. Contracts, invariants, tenant-isolation rules,
  accepted ADRs, the security/authz model.
- **Descriptive** — explains the system as designed (architecture overview, runtime narratives).
- **Informative** — helps the reader (glossary, orientation, context).

### The SentinelX safeguard

System documentation is the **authority** over: system boundary, module boundaries, contracts,
domain invariants, the tenant model, and global decisions. When service/client documentation is
written later (the Zoom-In phase), each one **starts from this System model and specializes it** —
no service may redefine a contract, an invariant, or the tenant model. Every important fact has
exactly one canonical home; other places reference it, never restate it as an independent copy.

---

## Source-of-truth map

| Knowledge | Canonical home |
|-----------|----------------|
| System boundary, actors, external dependencies | `00-overview/system-overview.md` |
| Domain concepts & terminology | `00-overview/glossary.md` |
| Teacher account & environment lifecycle | `03-domain/actor-lifecycles.md` |
| Free Trial → Subscription (access lifecycle) | `01-product/access-lifecycle.md` |
| Domain model & ownership | `03-domain/domain-model.md` |
| Domain invariants | `03-domain/invariants.md` (Normative) |
| Entity lifecycles (Session, Enrollment/Year) | `03-domain/lifecycles.md` |
| Architectural style, modules, boundaries | `04-architecture/architecture.md` |
| Internal API contract | `07-contracts/api-contract.md` (Normative) |
| External provider interfaces (LLM/Push/Video) | `07-contracts/external-interfaces.md` (Normative) |
| Architectural decisions | `10-decisions/ADR-*.md` (Normative) |
| Rejected & deferred decisions | `10-decisions/rejected-deferred.md` |

---

## Reading order

```
00-overview  →  03-domain  →  04-architecture  →  07-contracts  →  10-decisions
```

Start at `00-overview/system-overview.md` for a five-minute orientation, then read the domain
model before architecture (architecture assumes the domain vocabulary).

---

## Provenance note

Several V1 decisions **intentionally refined or superseded** the original project brief. Where
this happened, the relevant document records it explicitly (look for **Provenance** callouts).
This documentation preserves *why* decisions were made and what was rejected — not only the final
state — so a future reader can understand the reasoning, not just the result.
