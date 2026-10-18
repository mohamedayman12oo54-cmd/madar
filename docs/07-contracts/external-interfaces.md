# External Interfaces

> **Authority:** **Normative.** Modules MUST depend on these Madar-owned interfaces, not on
> provider-specific APIs.
> **Source of truth** for how Madar consumes its three external dependencies.
> **Depends on:** [ADR-002](../10-decisions/ADR-002-ai-internal-module.md),
> [ADR-009](../10-decisions/ADR-009-provider-interfaces.md), and the system boundary in
> `00-overview/system-overview.md`.

## Principle

All three external dependencies are consumed through **Madar-owned internal interfaces**. Domain and
application modules depend on the Madar contract, never on a provider's API. This keeps external
coupling behind explicit boundaries and preserves the option to change providers later without
changing domain/module semantics.

These are **internal modular-monolith boundaries**, not separate services or microservices. No
specific vendor or technology is selected at this stage — vendor selection is deferred.

## The three interfaces

### LLM interface
- **Consumed by:** the **Learning & AI** module only. No other module touches the LLM.
- **Purpose:** power the AI Study Assistant, AI Quiz generation, and State recommendation.
- **Boundary:** `Madar domain/application → Learning & AI module → LLM interface → external LLM`.
  The external model stays **outside** the system boundary; Madar owns orchestration, decision rules,
  and failure handling.
- **Behavior it must uphold:** asynchronous, failure-tolerant (ADR-006). The interface surfaces
  explicit success/failure so AI failures never block or corrupt deterministic state.

### Push Delivery interface
- **Consumed by:** the **Notifications** module.
- **Purpose:** deliver push notifications for the bounded V1 event set.
- **Boundary:** Madar stores push device tokens/registrations; **delivery** is external. Dispatch is
  asynchronous (ADR-005); a delivery failure does not affect the committed record or notification
  event.

### Video Storage / Delivery interface
- **Consumed by:** the **Content** module.
- **Purpose:** store and serve teacher-uploaded videos.
- **Boundary:** the video **binary/blob is external**; Madar stores video **metadata, targeting, and
  an external storage/delivery reference** — not the blob itself.

## Deferred (not part of this contract)

Specific vendors/providers for LLM, Push, and Video; the RAG/ingestion design for the Knowledge Base;
storage architecture and delivery mechanism for video; OTP/SMS provider mechanics for claiming
(claiming is an auth concern, not a notification channel). These are implementation/Operations
concerns and are intentionally not fixed here.

## Fourth interface: Payment Provider (Kashier) — a distinct trust boundary

Following the commercial-design pass (`01-product/commercial-model.md`), Madar consumes a payment
provider (Kashier) through a **fourth** Madar-owned interface, extending the ADR-009 pattern but
designed as its own shape because it is **not outbound-only** like the first three (see Negative space,
below, and `10-decisions/ADR-015-payment-provider-interface.md`).

- **Consumed by:** the **Billing** module (`10-decisions/ADR-014-billing-bounded-module.md`).
- **Purpose:** checkout initiation, recurring-agreement/token management, and payment-result
  processing for the Teacher↔Madar Subscription.
- **Boundary — outbound:** Madar calls Kashier to initiate a checkout or query status, same shape as
  the other three interfaces.
- **Boundary — inbound (the exception):** Kashier calls **into** Madar to report a payment result via a
  signature-verified webhook. This is the system's **only** approved inbound external integration — see
  `10-decisions/ADR-016-inbound-webhook-exception.md` for the narrow scope and required prerequisites
  (signature verification, event correlation, idempotent processing).
- **Boundary — browser redirect (not a trust boundary at all):** a browser return/redirect URL after
  checkout is **not** proof of payment and must never independently transition Subscription state —
  only the verified inbound webhook (or an internal reconciliation job polling Kashier's own
  status-lookup API) may do so.

## Negative space

The LLM, Push, and Video dependencies remain **outbound only**; none of them calls into Madar. The
**sole exception** in the system is the narrowly-scoped Kashier payment-result webhook described
above and in ADR-016 — it is the system's only approved inbound external integration. No other inbound
external integration exists, and this exception is not precedent for adding another without its own
dedicated ADR.
