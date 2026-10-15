# ADR-016 — Narrow, Approved Exception to "No Inbound Integrations": Kashier Payment-Result Webhooks

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted. **Amends** `07-contracts/external-interfaces.md` §Negative space and
`07-contracts/api-contract.md`'s "no inbound third-party integrations" negative-space statement to
carve out this single, named exception; both documents are updated as part of this decision pass to
reference this ADR rather than repeat the now-superseded blanket claim. Does not edit any other ADR. A
future change (a further inbound integration, or withdrawal of this one) requires a new superseding
ADR.

## Context
`07-contracts/external-interfaces.md` states, as a normative, current-state architectural claim: "The
three external dependencies are outbound only... there are no inbound external integrations in V1."
Kashier payment-result callbacks (webhooks) are inherently inbound — Kashier calls into Madar to report
a payment outcome. Proceeding with a Kashier integration without resolving this conflict would either
silently violate a documented invariant other code and future audits reasonably assume still holds, or
require building the webhook handler in a way that avoids ever calling it a webhook, which would be
worse (undocumented reality diverging from documented claim). Per the ADR register's own process
(`10-decisions/README.md`), a change of this kind — altering a stated negative-space invariant — is
architecturally significant enough to warrant a dedicated ADR rather than a silent doc edit.

## Decision
Kashier payment-result webhooks are an **approved, narrowly-scoped exception** to the system's
outbound-only external-integration posture. This is **not** a general reopening of "no inbound
integrations" — it applies **only** to Kashier payment-result callbacks, and only under these
prerequisites, which must all hold before any such endpoint is treated as safe to rely on:

1. **Signature verification** — every inbound Kashier request is cryptographically verified against a
   provider-issued secret before its payload is trusted; an unverified request is never processed.
2. **Event correlation** — every inbound event is correlated to an internal, provider-neutral
   Subscription/Invoice/PaymentAttempt record before any state transition is attempted; an
   uncorrelated event is rejected, not guessed at.
3. **Idempotent processing** — redelivery or duplication of the same provider event must not
   double-apply its effect (see ADR-017 for why this is a distinct mechanism from the existing AI
   client-request idempotency).

No other inbound integration is authorized by this ADR. Every other potential inbound integration
remains governed by the unchanged "no inbound integrations" posture unless and until its own ADR grants
a similarly narrow exception.

**Explicit trust-boundary distinctions (do not conflate):**
- **Outbound calls Madar makes to Kashier** (e.g., initiating a checkout) — ordinary outbound
  provider usage, same shape as the existing LLM/Push/Video calls.
- **Inbound, signature-verified Kashier webhook events** — the new exception this ADR grants; the
  **only** channel permitted to transition billing/subscription state based on a payment outcome.
- **Browser return/redirect URLs** — when a user's browser is redirected back to Madar after a Kashier
  checkout, that redirect is **not proof of payment** and must **never** independently activate a
  subscription or any paid capability. A redirect may improve UX (e.g., show a "payment received,
  confirming..." screen) but carries no trust weight.
- **Internal billing-state transitions** — only triggered by (a) a verified inbound webhook event, or
  (b) an internal reconciliation job polling Kashier's own status-lookup API (if one exists per external
  verification) — never by an unauthenticated inbound signal of any other kind.

## Alternatives considered
- **Do nothing / treat the existing claim as already satisfied** — rejected: it is factually false once
  a webhook endpoint exists, and silently building one anyway would leave the architecture
  documentation actively wrong, which the audits that discovered this conflict specifically flagged as
  a risk.
- **Blanket removal of the "no inbound integrations" rule** — rejected: far broader than what is
  actually needed; would remove a genuinely useful architectural invariant for every *other* potential
  future inbound integration, which is not warranted by this one, narrow, needed exception.
- **Treat the browser return/redirect URL as sufficient proof of payment, avoiding a true webhook** —
  rejected: this is a well-known integration anti-pattern (the user can navigate to the return URL
  without ever paying, or the browser tab can be closed before the redirect fires); it would be
  materially less safe than a verified webhook and was explicitly rejected on that basis.

## Consequences
- `07-contracts/external-interfaces.md` §Negative space and `07-contracts/api-contract.md`'s negative-space
  bullet are both updated (this decision pass) to reference this ADR and scope the exception precisely,
  rather than repeating the now-superseded universal claim.
- `docs/diagrams/system/system-context.mmd` is updated to show Kashier as both an outbound dependency
  and the source of the one approved inbound integration, no longer lumped into "Out of V1 context."
- A future webhook endpoint (not built by this ADR) must satisfy all three prerequisites above before
  it is considered production-ready; this ADR does not itself implement signature verification, event
  correlation, or idempotent processing — see ADR-015 and ADR-017 for the related interface/idempotency
  decisions, and the future Implementation Plan for the actual build.
- No other module or future feature may cite this ADR as precedent for adding its own inbound
  integration without its own dedicated ADR.
