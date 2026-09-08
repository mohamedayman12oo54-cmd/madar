# Operations — Knowledge Base Lifecycle

> **Authority:** Normative (KB operational lifecycle).
> **Depends on:** `01-product/scope.md` (AI source boundaries), `07-contracts/external-interfaces.md`.

The central educational Knowledge Base is **product-owned** and **centrally curated** by the Content
Maintainer. Teachers do **not** curate AI sources in V1 (the AI Study Assistant works out of the box;
the AI Quiz uses teacher-provided content instead).

## Lifecycle: draft → published/versioned

- Content Maintainers edit **draft** content; only **published** content is authoritative for AI
  consumption.
- The versioning model is intentionally **lightweight**; V1 does not require a complex content-
  publishing platform.
- If published content requires asynchronous processing/indexing for AI consumption, that processing
  may run as a **background job on the worker process** (ADR-012).

## Deferred

The specific RAG/ingestion infrastructure, retrieval, grounding strategy, and KB store technology are
**deferred** to implementation/AI Engineering. Do not introduce a specific design here unless the
actual KB implementation requires it.
