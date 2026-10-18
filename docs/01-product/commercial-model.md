# Commercial Model — Plans, Trial, Billing Cycle (Teacher ↔ Madar)

> **Authority:** Normative for the commercial rules stated below (plan definitions, trial parameters,
> billing-cycle mechanics, failed-payment policy direction, access-not-granted principle). This
> document is the **authoritative source** for these numbers; `01-product/access-lifecycle.md`
> describes the lifecycle's existence/shape and now points here for the resolved parameters instead of
> duplicating them.
> **Depends on:** `01-product/access-lifecycle.md`, `03-domain/actor-lifecycles.md`,
> `03-domain/invariants.md` (INV-9), `10-decisions/ADR-013-permanent-environment-cardinality.md`,
> `10-decisions/ADR-014-billing-bounded-module.md`.
> **Scope note:** this is a **commercial-design-pass** document. It records confirmed commercial
> decisions as **approved product rules**. It deliberately does **not** design schema, endpoints, or
> implementation — that is a later Implementation Plan phase, not performed here. Every item explicitly
> marked **Open** below is genuinely undecided; do not treat silence elsewhere as a decision either way.

## Commercial ownership unit

`Teacher Account → exactly one Teacher Environment → that Environment's Subscription.`

This is now a **permanent** domain rule (not a V1-only limitation): one Teacher Account owns exactly
one Teacher Environment (see INV-9, `ADR-013-permanent-environment-cardinality.md`). A teacher who
wants a second, separate environment creates another account. The Subscription is therefore scoped to
the Teacher Account/Environment pair as a single commercial unit — there is no multi-environment
billing-sharing concept in V1 or beyond.

**Distinct from `financials` — do not conflate.** `financials` (the `MonthlyPayment` model) tracks
whether a **student** has paid their **teacher's** Grade fee. Billing (this document) is the
**Teacher ↔ Madar** commercial relationship. These are two unrelated money concepts and must never be
merged, reused, or cross-referenced as if they were the same feature. See
`00-overview/glossary.md` and `06-data/data-model.md`.

## Plans (exactly three; no additional tiers, no annual billing, no discounts)

| Plan | Price | Billing period | Student cap | Feature set |
|------|-------|-----------------|-------------|-------------|
| **Plan 1** | EGP 1,000 | 30 elapsed days | Max 400 students | All standard (non-AI) platform features + AI quiz-generation-from-video **only** (no other AI capability) |
| **Plan 2** | EGP 1,500 | 30 elapsed days | Max 800 students | Everything in Plan 1 + AI chat about video-lesson content |
| **Plan 3** | EGP 2,000 | 30 elapsed days | No plan-level numerical student cap | Everything in Plan 2 + AI-assisted student-performance analysis (attendance, recitation, quizzes, video-watch ratio) |

These are the only three paid plans. No additional tier, no annual/long-cycle billing option, and no
discount mechanism exist or are implied.

### Plan 3 future-feature rule (precise statement — do not oversimplify)

Plan 3 includes all **current and future** standard and advanced platform features **by default**.
This is **not** an unconditional promise of unlimited externally-costed resource consumption: a future
feature that carries a **distinct, variable external cost** (e.g., unusually expensive AI inference,
storage, or delivery) **may** be priced or announced separately, at Madar's discretion, even for Plan 3
subscribers. Plan 3's default-inclusion rule applies to feature **availability**, not to an open-ended
commitment to absorb arbitrary future external costs. The exact mechanism for identifying/flagging such
a separately-priced future feature is **Open** (see Open Items below).

## Free trial

- **Duration:** exactly **16 days**.
- **Start:** the trial starts at the instant the Teacher Account is activated **and** its Environment is
  successfully established — in the current signup flow this is a **single atomic event**
  (`TeacherSignupEnvironmentView.post`, one `transaction.atomic()` block creating the User, the
  Environment, and the owner Membership together; see the Kashier readiness audits for the code
  citation). The trial-start instant is this recorded **Backend-authoritative** activation timestamp —
  **never** client/browser-supplied time, and **never** calendar-month arithmetic. The trial window is
  16 elapsed days from that instant, computed server-side.
- **No payment card required** to start the trial.
- **Feature set during trial:** the full **Plan 3** feature set.
- **Student cap during trial:** max **250 students** (a trial-specific cap, independent of and smaller
  than any paid plan's cap).
- **No auto-conversion:** the trial does **not** automatically convert to a paid subscription. After
  expiry, the teacher must explicitly choose and pay for a plan to regain/continue access.
- **Repeat-trial / anti-abuse policy:** explicitly **Open** — not decided, not defaulted. See Open Items.

## Billing period & renewal

- **Billing period:** exactly **30 elapsed days** — never described or implemented as "calendar month,"
  even where an external provider API defaults to a monthly billing option. This is a deliberately
  precise business rule distinct from the `financials` app's calendar-month cadence
  (`config/months.py`), which is an unrelated concept and must not be reused for subscription billing.
- **Auto-renewal:** an intended capability for subscriptions enrolled in an appropriate
  recurring-payment agreement with the payment provider.
- **Cancellation:** takes effect at the **end of the already-paid period**. Cancellation stops the
  **next** renewal only — it does **not** immediately terminate the current paid period's access, and
  it does **not** itself imply a refund (refund eligibility is a separate, open question).

## Failed renewal — policy direction only (no invented numbers)

The following are approved **directional** rules; exact numeric parameters are explicitly **not**
decided here:

- A **single** failed renewal attempt must **not** immediately terminate access.
- A **limited** number of retries is expected.
- A **clear notification** to the teacher plus recovery instructions is expected.
- A **grace period** is expected before access is restricted.
- Any **ambiguous outcome** (e.g., a delayed or duplicated provider event) must be reconciled before
  risking a duplicate charge.

**Not decided (do not infer a default):** exact retry count, retry timing/schedule, and grace-period
duration. See Open Items.

## Access-not-granted principle

When access is not granted (expired trial, or failed/unresolved billing), the following principle is
approved:

- The Teacher Account and its data must **never** be destroyed or become unrecoverable.
- The Teacher must retain the ability to: **authenticate**, **manage/resolve billing**, and have an
  **appropriate path to review/export their own data**.
- Paid-educational-capability gating must be **Backend-enforced**, not merely hidden in the Frontend.

**Not decided (do not infer a default):** the exact student-facing restricted-access behavior, and the
complete teacher-facing read-only permission ruleset while access is not granted. These remain **Open**
— see Open Items and `services/backend/01-scope/teacher-access-lifecycle.md` (TAL-5).

## Open items (explicitly unresolved — do not invent defaults)

| Item | Status |
|------|--------|
| Exact failed-renewal retry count/schedule | Open |
| Exact grace-period duration | Open |
| Student-facing restricted-access behavior (exact rules) | Open |
| Teacher-facing read-only permission ruleset post-expiry (exact endpoints/scope) | Open |
| Repeat-trial / trial-abuse controls | Open |
| AI usage quotas / cost controls (ties to the Plan 3 future-feature rule) | Open |
| Upgrade/downgrade timing and proration policy | Open |
| Refund eligibility and process | Open |
| Existing-subscriber treatment on future price changes | Open |
| Invoice/receipt/tax requirements | Open |
| Kashier's exact recurring-agreement consent requirements | Open — external verification required |
| Provider-specific ambiguous-outcome recovery procedure | Open — external verification required |
| Concrete production scheduling/monitoring for renewal/reconciliation jobs | Open — operational verification required |
| Whether Kashier's "RECURRING"/"MONTHLY" agreement product supports an exact 30-elapsed-day interval vs. only a calendar-month schedule | **Open — launch/design gate pending Kashier clarification** (see `services/backend/07-contracts/external-api-alignment.md`) |

## Architectural direction (summary; detail in Backend/ADR docs)

- Billing is an independent bounded Backend module (`billing`) within the existing Modular Monolith —
  `10-decisions/ADR-014-billing-bounded-module.md`.
- Kashier is consumed through a Madar-owned payment-provider interface, following the ADR-009 pattern
  but as its own trust boundary — `10-decisions/ADR-015-payment-provider-interface.md`.
- Kashier's inbound payment-result webhook is an approved, narrowly-scoped exception to the system's
  outbound-only external-integration posture —
  `10-decisions/ADR-016-inbound-webhook-exception.md`,
  `07-contracts/external-interfaces.md`.
- Webhook-event safety is distinct from the existing AI client-request idempotency mechanism —
  `10-decisions/ADR-017-payment-event-idempotency.md`.
- Billing owns the entitlement/access-policy decision; enforcement integrates with, but is not folded
  into, the existing composite authorization/tenant model —
  `10-decisions/ADR-018-billing-entitlement-boundary.md`.

## External verification context (Kashier) — not treated as settled design

Recorded here as **external facts requiring separate verification**, reviewed as of **2026-10-15**, not
as decisions made by Madar:

- Kashier's recurring-payments guide
  ([developers.kashier.io/docs/accept-payments/recurring](https://developers.kashier.io/docs/accept-payments/recurring))
  states Kashier has **no managed subscriptions/billing-plans API**; the merchant owns the billing
  schedule, stores the token/agreement from a successful initial setup, and charges that saved token
  each cycle. The published example includes `agreement.type = RECURRING`,
  `paymentFrequency = MONTHLY`, `minimumDaysBetweenPayments`.
- Webhooks: [developers.kashier.io/docs/webhooks](https://developers.kashier.io/docs/webhooks) and
  [developers.kashier.io/docs/webhooks/payloads](https://developers.kashier.io/docs/webhooks/payloads) —
  the webhook contract (including signature verification and mode-specific credentials) must come from
  these, not be invented.
- Going live:
  [developers.kashier.io/docs/get-started/going-live](https://developers.kashier.io/docs/get-started/going-live) —
  production activation, live webhook configuration, and smoke-test requirements need operational
  verification before launch.
- **Critical, unresolved:** Kashier's own documentation does not establish whether a `RECURRING`
  agreement guarantees an exact 30-elapsed-day interval or only a calendar-month schedule. This is
  marked as an explicit **launch/design gate** pending Kashier clarification — not resolved in either
  direction by this document.
