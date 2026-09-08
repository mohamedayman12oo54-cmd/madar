# Access Lifecycle — Free Trial & Subscription

> **Authority:** Descriptive (canonical for the Teacher's commercial/access lifecycle at the system
> level).
> **Source of truth** for the *existence and purpose* of the Free Trial → Subscription lifecycle.
> **Depends on:** `01-product/product.md`, `03-domain/actor-lifecycles.md`.
> **Scope note:** this document establishes that Madar has a commercial/access lifecycle and what it
> means for access. It deliberately does **not** specify pricing, plans, billing provider, payment
> gateway, invoicing, trial duration, renewal/cancellation mechanics, or accounting behavior — all of
> which are **unresolved/deferred**. It does not touch student fee-tracking, which is a separate
> concept (see below).

## Why this exists

The lifecycle audit found that Madar had no documented commercial/access lifecycle — a Teacher was
called "Primary customer" with no documented way to become or remain one, and no documented access
ending. This document closes that gap at the system level.

## The lifecycle

```
Teacher enters Madar (product entry / account creation)
        │
        ▼
Free Trial  ── the Teacher uses Madar as their own educational environment during the trial
        │
        ▼
Trial ends
        │
   ┌────┴─────────────────────────┐
   ▼                              ▼
Teacher subscribes            Teacher does not subscribe
   │                              │
   ▼                              ▼
Continued access              Continued access depends on subscription
(active subscription)         (access no longer granted by an active trial/subscription)
```

- **Free Trial.** A Teacher can **start using Madar through a Free Trial**. During the trial the
  Teacher creates their account, establishes their environment, and uses the product's documented
  capabilities as their own educational environment (`03-domain/actor-lifecycles.md`).
- **Trial → Subscription.** After the Free Trial ends, the Teacher can **subscribe and continue
  using Madar**. Subscription is the mechanism by which continued access is granted after the trial.
- **Purpose.** The lifecycle's system-level meaning is simply: **whether a Teacher currently has
  access** is governed by their trial/subscription state. The intent is
  *discover → account → environment → trial usage → subscription → continued use.*

## Access dependency (terminal/continuation states)

At the system level, continued access to the Teacher Environment and its capabilities depends on the
Teacher's access state:

- **During Free Trial:** access is granted by the active trial.
- **After trial, with subscription:** access continues.
- **After trial, without subscription:** continued access depends on subscription — i.e., an active
  trial or subscription is what grants ongoing access.

This removes the previously unexplained "no commercial ending": access is no longer assumed to be
perpetual and unconditional.

> **Unresolved (do not assume):** the exact behavior when access is not granted — whether the
> environment is suspended, becomes read-only, enters a grace period, or is otherwise handled, and any
> data-retention consequence — is **not decided** here. The existing data-retention stance
> (`06-data/lifecycle-retention.md`: indefinite retention, no deletion workflow in V1) remains the
> only documented retention rule and is unchanged. Suspension/grace/cancellation mechanics are
> deferred (`10-decisions/rejected-deferred.md`).

## Distinct from student fee tracking (do not conflate)

Two different money concepts exist in Madar and must not be merged:

| Concept | What it is | Where documented |
|---------|-----------|------------------|
| **Commercial relationship (Madar ↔ Teacher)** | The Teacher's trial/subscription access to Madar itself | this document |
| **Student payment / fee tracking (inside the environment)** | The Teacher recording a student's monthly Grade fee status | `02-requirements/functional.md` §Payments, `06-data/`, INV-5 |

The existing student payment feature is **record-only fee tracking inside the educational
environment** ("Madar records payment information; it is not an accounting/payment platform" —
`01-product/scope.md`). It is unrelated to how the Teacher pays for Madar. Neither definition changes
the other.

## Deferred commercial mechanics

Explicitly **not decided** and not invented here: pricing, plans/tiers, payment provider/gateway,
billing/invoicing, exact **trial duration**, renewal mechanics, cancellation UX, financial
accounting, and proration. These are recorded as deferred (`10-decisions/rejected-deferred.md`) and
belong to a later commercial-design pass, not to this system-lifecycle correction.
