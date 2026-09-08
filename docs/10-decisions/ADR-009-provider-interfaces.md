# ADR-009 — Consume External Providers Behind Madar-Owned Interfaces

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
Madar depends on three external systems: an LLM provider, push-notification delivery, and video storage/streaming. Directly coupling modules to provider APIs would make providers hard to change and would leak provider concerns into the domain. ADR-002 already established this principle for AI; it should generalize.

## Decision
Consume all three dependencies through **Madar-owned internal interfaces** — an LLM interface, a Push Delivery interface, and a Video Storage/Delivery interface. Modules depend on the Madar contract, not the provider API. These are internal modular-monolith boundaries, not separate services.

## Alternatives considered
- **Direct provider coupling** — rejected: locks Madar to specific vendors and leaks provider details into modules.
- **A separate integration service per provider** — rejected for V1: unnecessary operational cost; internal interfaces suffice within one deployable.

## Consequences
- Providers are swappable without changing domain/module semantics.
- Three stable internal seams (LLM used only by Learning & AI; Push by Notifications; Video by Content).
- Specific vendors remain deferred; still one deployable.
