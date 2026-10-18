# ADR-017 — Payment-Event Integrity Is Distinct From Client-Request Idempotency

> **Authority:** Normative · **Status:** Accepted

## Status
Accepted. Extends ADR-011 (Selective Idempotency) by establishing that a **new, distinct** mechanism is
required for payment-provider events; it does not edit or weaken ADR-011, which remains fully accurate
for its original scope. A future change requires a new superseding ADR.

## Context
ADR-011 establishes selective, client-key-based idempotency for retryable commands — concretely,
`ai/models.py`'s `idempotency_key` field and its `UniqueConstraint(fields=["environment",
"requested_by","idempotency_key"], condition=Q(idempotency_key__isnull=False))`. This mechanism
prevents the **same calling user**, in the **same environment**, from creating a duplicate AI operation
on retry. Both backend-readiness audits independently confirmed this mechanism solves **client-request
dedup**, not **provider-event dedup** — it has no concept of an externally-generated event ID, no
replay-window semantics, no notion of "received but not yet processed" distinguishable by a third
party, and no protection against a duplicated or replayed webhook POST from Kashier itself. Assuming
this existing mechanism "already covers" webhook safety, merely because the word "idempotency" and a
working unique-constraint pattern already exist in the codebase, would be a safety-relevant
misapplication.

## Decision
Payment-event integrity requires a **logically separate set of guarantees** from the existing AI
client-request idempotency mechanism. These are distinct concerns and must not be collapsed into one
mechanism or one field:

- **Client-request idempotency** (existing, ADR-011/`ai/models.py`) — prevents a caller's own
  double-submit/retry from creating duplicate Madar-initiated records. Unchanged, unaffected, and
  explicitly **not** reused as-is for the concerns below.
- **Provider-event deduplication** — the same Kashier event (identified by Kashier's own event/
  transaction id) must not be double-applied if Kashier redelivers it.
- **Provider signature/auth verification** — a prerequisite to trusting an inbound event at all (see
  ADR-016); dedup only matters once a request is already known to be genuinely from Kashier.
- **Payment-attempt tracking** — recording each attempt (initiated, pending, succeeded, failed) as its
  own auditable record, independent of how many webhook deliveries report on it.
- **Invoice state** — the billing-period-level record of what was owed and whether it was satisfied.
- **Subscription state** — the current access-governing state (trialing, active, past_due, cancelled,
  etc. — exact state names not fixed by this ADR).
- **Entitlement state** — what the Subscription's current state currently permits (ADR-018).
- **Reconciliation of ambiguous/delayed outcomes** — a status-lookup/reconciliation path for when a
  webhook is missed, delayed, or arrives ambiguously, distinct from the webhook-receipt path itself.

**Explicit safety statements:**
- A webhook **arriving** is not, by itself, sufficient proof of a successful payment — signature
  verification, event correlation, and the event's own payload outcome (success/failure/refund) must
  all be checked.
- A browser redirect must **never** independently activate a subscription or any paid capability (see
  ADR-016).

This ADR does not invent a schema for any of the above — it establishes the required logical separation
and the invariants each piece must uphold; concrete fields/tables are an Implementation Plan concern.

## Alternatives considered
- **Extend the existing `idempotency_key`/`UniqueConstraint` mechanism to also cover webhooks** —
  rejected: it is scoped to `(environment, requested_by)`, which has no meaning for a provider-pushed
  event with no requesting Madar user; forcing it to fit would either weaken its existing guarantee or
  require a confusing dual-purpose field.
- **Treat "idempotency" as a single, generic cross-cutting concept needing only one implementation** —
  rejected: client-retry dedup and provider-event dedup solve different problems with different failure
  modes (a client retry is trusted and same-origin; a webhook redelivery is untrusted and third-party),
  and conflating them was explicitly identified as a risk by the audits.

## Consequences
- The future `billing` module's event-processing design (not performed here) must implement
  provider-event dedup, signature verification, and attempt/invoice/subscription/entitlement state as
  logically separate concerns, per this ADR, rather than reusing `ai/models.py`'s pattern as a
  shortcut.
- `services/backend/07-contracts/external-api-alignment.md` is updated (this decision pass) to state
  this distinction explicitly for the Backend's own contract documentation.
- Reconciliation (ambiguous/delayed/missed webhook outcomes) is named as a required capability; its
  concrete mechanism (e.g., a status-lookup job modeled on the existing atomic-claim worker pattern in
  `ai/management/commands/process_ai_operations.py` rather than the non-claiming pattern in
  `notifications/management/commands/process_notifications.py`) is an implementation choice, not fixed
  by this ADR.
