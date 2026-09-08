# ADR-002 — Keep AI as an Internal Bounded Module in V1

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted (V1). Supersedes nothing. A future change requires a new superseding ADR.

## Context
AI (Study Assistant, Quiz, State recommendation) is a first-class V1 capability, owned by a dedicated AI Engineer. The underlying model is an external LLM provider. The question is whether AI should be a separate service or an internal module.

## Decision
AI is an **internally bounded module** within the Modular Monolith, exposing a clean internal interface. The rest of the domain never depends on LLM-provider details. Boundary: `Madar domain/application → AI module → external LLM provider`.

## Alternatives considered
- **Separate AI service** — rejected for V1: adds an operated component without a present driver (AI-specific scaling, latency isolation, deployment independence) strong enough to justify it. The existence of a dedicated AI Engineer is not, by itself, sufficient reason to split.

## Consequences
- Single deployable preserved; AI Engineer can own the module independently.
- A strong seam remains that could later allow extraction into a separate service if real AI-specific requirements emerge.
- Provider details stay isolated behind the AI module (reinforced by ADR-009).
