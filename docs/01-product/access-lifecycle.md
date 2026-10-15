# Access Lifecycle — Free Trial & Subscription

> **Authority:** Descriptive (canonical for the Teacher's commercial/access lifecycle at the system
> level).
> **Source of truth** for the *existence and purpose* of the Free Trial → Subscription lifecycle.
> **Depends on:** `01-product/product.md`, `03-domain/actor-lifecycles.md`.
> **Scope note:** this document establishes the **existence and shape** of the commercial/access
> lifecycle. The concrete commercial parameters (pricing, plans, trial duration, billing cycle,
> renewal/cancellation mechanics, failed-payment policy direction, and the access-not-granted
> principle) are now **decided and authoritatively recorded** in
> [`commercial-model.md`](commercial-model.md) — this document does not duplicate them and defers to
> that document for all numbers. What remains genuinely open after that commercial-design pass (exact
> retry/grace numbers, student-facing restricted-access behavior, refunds, proration, etc.) is listed
> there, not invented here. It does not touch student fee-tracking, which is a separate concept (see
> below).

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

> **Principle decided; exact mechanics remain open.** The access-not-granted **principle** is now
> decided (`commercial-model.md` §Access-not-granted principle): the account/data are never destroyed;
> the Teacher retains authentication, billing-resolution, and data-review/export access; paid-capability
> gating is Backend-enforced. The **exact** student-facing restricted-access behavior and the complete
> teacher read-only permission ruleset remain **not decided** — see `commercial-model.md` §Open items.
> The existing data-retention stance (`06-data/lifecycle-retention.md`: indefinite retention, no
> deletion workflow in V1) remains the only documented retention rule and is unchanged.

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

## Commercial mechanics — now resolved by a commercial-design pass

Pricing, plans/tiers, free-trial duration, billing-cycle mechanics, renewal/cancellation, and the
failed-payment policy direction are **no longer deferred** — they are decided and authoritatively
recorded in [`commercial-model.md`](commercial-model.md), which is the product of the commercial-design
pass this document previously named as the resolution path (`10-decisions/rejected-deferred.md`).
Financial accounting, proration, refund policy, and several other specific sub-items remain explicitly
**open** — see `commercial-model.md` §Open items; they are not resolved by implication here.
