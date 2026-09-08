# Internal Module-Capability Contract Style

> **Authority:** **Normative** (a Backend contract-level architectural rule).
> **Specializes:** `../../../04-architecture/building-blocks.md`,
> `../03-internal-boundaries/module-boundaries.md`.
> **Design-first note:** this asserts a **style** for internal contracts. It does **not** prescribe a
> concrete representation (interface syntax, DTO types, exception classes). Representation is Open.

The Backend establishes a uniform **style** for internal module-capability contracts, distinct from
the external REST/API contract (`external-api-alignment.md`). This is how modules collaborate under the
"capabilities, not direct persistence access" rule (`../03-internal-boundaries/module-boundaries.md`,
BND-1).

## The style

At the appropriate level of abstraction, every internal module-capability contract has:

- an explicit **capability** (what the owning module offers);
- explicit **inputs / context** (including the applicable trusted execution context and
  tenant/relationship scope where relevant);
- explicit **result semantics**;
- explicit **failure semantics**;
- respect for **module persistence ownership and privacy** (the caller never reaches into the
  provider's persistence);
- an explicit **dependency direction** consistent with the established module boundaries.

## What this is and is not

- This is a **contract-level architectural rule**, not an implementation prescription. The concrete
  representation of these contracts remains **Open** for later implementation refinement.
- It applies to cross-module collaboration inside the Backend. The **Backend ↔ AI** integration is a
  specific, collaboratively-owned instance of an internal capability contract and is defined
  separately in `backend-ai-integration-contract.md`.

## Relationship to failure semantics

Internal capability failures must not bypass the established authorization, tenant-isolation, or
invariant semantics. Where an internal failure is surfaced through a client-facing boundary, it honors
the existing uniform client-facing error/operation semantics — the **semantic** mapping is asserted in
`external-api-alignment.md`, while the exact serialized taxonomy is deferred.
