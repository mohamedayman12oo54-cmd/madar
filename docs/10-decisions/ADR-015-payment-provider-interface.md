# ADR-015 — Madar-Owned Payment-Provider Interface, Extending ADR-009 as a Distinct Trust Boundary

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted. Supersedes nothing. Extends ADR-009 with a fourth provider interface that is explicitly
**not** assumed to share implementation shape with the first three. A future change requires a new
superseding ADR.

## Context
ADR-009 establishes that Madar consumes external providers (LLM, Push, Video) through Madar-owned
internal interfaces, concretely realized today as `content/providers.py` and `ai/providers.py` (an
abstract base class + settings-selected factory). A Kashier payment-provider integration is a natural
fourth instance of this pattern — but payments carry a materially different trust boundary than the
first three: Kashier is the system's first **inbound**-capable provider (ADR-016), handles money
movement, and requires signature verification and event-integrity guarantees none of the existing three
providers need. Reusing the existing `VideoProvider`/LLM-provider interface shapes as-is, merely
substituting Kashier for the vendor, would risk quietly importing assumptions (e.g., `verify_webhook`
returning `False` unconditionally because "nothing external calls us," per
`content/providers.py`) that are actively wrong for a real inbound payment callback.

## Decision
Consume Kashier through a **new, Madar-owned payment-provider interface**, following ADR-009's general
principle (modules depend on a Madar contract, not the vendor API) but designed as its **own** shape,
with these distinct concerns kept separate rather than collapsed into one interface method set:
1. **Provider-neutral billing decisions** — what Madar decides about plans/entitlements/trial,
   independent of which payment provider is used.
2. **Madar-owned payment-provider contract** — the abstract interface a Kashier adapter (and any future
   alternative provider) implements.
3. **Kashier-specific adapter** — the concrete implementation of (2) for Kashier.
4. **Inbound event verification + translation** — signature verification, raw-body handling, and
   translation of a Kashier webhook payload into an internal, provider-neutral event.
5. **Internal state transitions** — how a verified, translated event is applied to Subscription/Invoice/
   PaymentAttempt state, which must never be reachable except through (4)'s verified output.

This interface belongs to the `billing` module (ADR-014), is selected by configuration following the
existing `VIDEO_PROVIDER`/`AI_PROVIDER` env-var-factory convention (a hypothetical `PAYMENT_PROVIDER=
kashier`), and is the **fourth** instance of the ADR-009 pattern — but its webhook-facing portion (4) is
new territory the first three instances do not need, since Video/LLM/Push are outbound-only
(ADR-016 governs the inbound exception itself).

## Alternatives considered
- **Reuse `VideoProvider`'s `verify_webhook` shape as-is for Kashier** — rejected: that method exists
  only as an unimplemented interface stub (`LocalStorageProvider.verify_webhook` always returns
  `False`); treating it as a working precedent for payment-webhook verification would be a false sense
  of readiness, not an actual security control.
- **Treat payments as just another ADR-009 instance with no special-casing** — rejected: it would blur
  the one trust-boundary distinction (inbound, money-moving, signature-verified) that materially
  differs from the first three providers and that a future engineer must not miss.
- **Build the Kashier integration directly against Kashier's SDK/API with no Madar-owned interface** —
  rejected: contradicts ADR-009's established principle and would lock billing logic to Kashier's
  specific API shape.

## Consequences
- A future Kashier adapter implementation sits behind a Madar-owned interface, consistent with ADR-009,
  but is not required or assumed to share a base class or method signatures with `VideoProvider`/the LLM
  provider interface.
- The separation of concerns (1)-(5) above is binding guidance for how the `billing` module's
  payment-provider boundary is designed in the future Implementation Plan; no schema or code is created
  by this ADR.
- Signature verification, raw-body preservation, and event-correlation/idempotent processing are
  established as **prerequisites** of (4), not optional hardening to add later — see ADR-017 for the
  idempotency/event-integrity distinction this implies.
