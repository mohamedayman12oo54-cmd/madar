# Billing (Kashier) API — Frontend hand-off

> **BILL-WU-032.** Status: **READY WITH A TRACKED OPEN ITEM** — the restricted-access UI contract
> (BILL-DEC-02 portions) is not decided yet; those sections are marked **PENDING** below and must
> not be guessed at or implemented ahead of that decision.
> **Grounded at:** `apps/backend/billing/*` as implemented by BILL-WU-011, 012, 019, 028, 031
> (all VERIFIED). **Authority:** this document describes what the Backend actually returns; it does
> not invent new behaviour. Where the Backend's own serializers are themselves marked PROPOSED
> (not yet a frozen contract — `serializers.py`'s own module docstring), that is repeated here.
>
> **The one rule that matters most:** a redirect back from Kashier to
> `GET /api/v1/billing/checkout/return/` means **"pending confirmation," never "paid."** Only a
> verified webhook (server-to-server) or the teacher's own later poll of the Subscription/history
> endpoints can ever confirm payment (ADR-016). The Frontend must never read success from the
> redirect itself — not from a query string, not from the mere fact that the user came back.

## Endpoints

All routes are under `/api/v1/billing/`. Every route except the webhook requires
`Authorization: Bearer <token>` (Teacher) **and** the active-environment header
(`IsEnvironmentMember.for_role("owner")` — the caller must be the OWNER member of their own
environment; no body field ever selects the tenant). Checkout, checkout-return and cancel are
**always reachable**, even when `entitlement.access_granted` is `false` — billing resolution is one
of the always-permitted categories (commercial-model §Access-not-granted), so a locked-out teacher
can still open their own billing page and act on it.

### `GET /api/v1/billing/plans/`

The global plan catalog. No environment header consulted (not tenant-scoped data).

Response `200`:
```json
[
  {"key": "plan_1", "name": "Plan 1", "price_minor_units": 100000, "currency": "EGP", "max_students": 250},
  {"key": "plan_2", "name": "Plan 2", "price_minor_units": 150000, "currency": "EGP", "max_students": 400},
  {"key": "plan_3", "name": "Plan 3", "price_minor_units": 200000, "currency": "EGP", "max_students": null}
]
```
`price_minor_units` is piastres (divide by 100 for EGP display). `max_students: null` means no cap.

### `GET /api/v1/billing/subscription/`

The caller's environment's subscription/trial status plus its entitlement summary.

Response `200`:
```json
{
  "plan_key": "plan_1",
  "trial_end": "2026-11-01T12:00:00Z",
  "current_period_end": "2026-12-01T12:00:00Z",
  "cancel_at_period_end": false,
  "entitlement": {
    "access_granted": true,
    "basis": "trial_active",
    "reason_code": "trial_active",
    "capabilities": ["ai.performance_analysis", "ai.quiz_from_video", "ai.video_content_chat"],
    "student_cap": 250
  }
}
```
- `plan_key`/`trial_end`/`current_period_end` are `null` when not applicable (e.g. no Subscription
  yet, or no plan chosen).
- `entitlement.basis`/`reason_code` are stable string enums — see **Entitlement reason codes**
  below. This is the one place the Frontend should read to decide what to show for "why can't I use
  this," rather than inferring it from a 403 on some other feature endpoint.
- `student_cap: null` means no numeric cap (Plan 3).

### `GET /api/v1/billing/history/`

Paginated (`StandardPagination` — standard `count`/`next`/`previous`/`results` envelope), newest
first. Each row:
```json
{
  "id": 42,
  "status": "succeeded",
  "amount_minor_units": 100000,
  "currency": "EGP",
  "created_at": "2026-10-01T12:00:00Z",
  "period_start": "2026-10-01T12:00:00Z",
  "period_end": "2026-10-31T12:00:00Z"
}
```
`status` is one of `initiated`, `pending`, `succeeded`, `failed`, `unknown` (`unknown` means "still
being reconciled with Kashier" — show it as pending/processing, never as a failure).
`period_start`/`period_end` are `null` for a checkout attempt that never completed (no period was
created). No provider/correlation identifiers are exposed here by design.

### `POST /api/v1/billing/checkout/`

Body: `{"plan_key": "plan_1"}` (one of `plan_1`/`plan_2`/`plan_3`). Any other field sent is silently
ignored — it is never read server-side (not a bug to work around; a deliberate anti-mass-assignment
guarantee).

Response `201`:
```json
{"session_url": "https://test-api.kashier.io/pay/...", "attempt_id": 123}
```
Redirect the teacher to `session_url`. After they return, poll `checkout/return/` (below) and/or
`subscription/` — never treat the redirect itself as confirmation.

Error responses (both carry `{"detail": "<human message>", "code": "<stable code>"}`):

| HTTP | `code` | Meaning |
|---|---|---|
| 400 | `invalid_plan` | Unknown or inactive plan key. |
| 409 | `paid_period_active` | A paid period is already active; plan changes mid-period are not supported. |
| 400 | `provider_unavailable` | Kashier could not be reached; retry later. |

### `GET /api/v1/billing/checkout/return/?attempt_id=123`

**Display only.** Never writes any state, regardless of what the query string claims.

Response `200`:
```json
{"attempt_id": 123, "status": "pending"}
```
`attempt_id`/`status` are both `null` if the id is missing, not found, or belongs to a different
environment (never an error — just "nothing to show"). `status` is the same enum as the history
endpoint. **Show "pending confirmation," never "paid," for any status other than `succeeded`.**

### `POST /api/v1/billing/subscription/cancel/`

No body. Idempotent — calling it again when already cancelled returns the same shape.

Response `200`:
```json
{"cancel_at_period_end": true, "renewal_already_in_progress": false, "renewal_attempt_status": null}
```
- Access continues through the end of the current paid period (never immediate); no refund is ever
  issued (out of scope for this plan).
- `renewal_already_in_progress: true` means a renewal charge for the *next* period had already
  started before this cancel request landed — it cannot be aborted. `renewal_attempt_status` is then
  one of `initiated`/`pending`/`unknown`. Surface this plainly ("a renewal charge is already in
  progress and could not be stopped") rather than implying the cancel failed.

Error response `404`: `{"detail": "No subscription exists for this environment.", "code": "no_subscription"}`.

### Webhook (server-to-server only — not a Frontend concern)

`POST /api/v1/billing/webhooks/kashier/` is the one unauthenticated route this module adds. It is
called by Kashier, never by the Frontend, and is listed here only so it is not mistaken for a
client-facing endpoint.

## Stable error codes (cross-endpoint)

These are machine-readable (`code`) and intentionally separate from the human `detail` message —
branch on `code`, localize/display `detail` or your own copy, never parse `detail`.

| `code` | Raised by | Meaning |
|---|---|---|
| `invalid_plan` | checkout | Unknown/inactive plan. |
| `paid_period_active` | checkout | Plan change blocked mid-period. |
| `provider_unavailable` | checkout | Transient Kashier failure. |
| `no_subscription` | cancel | Nothing to cancel. |
| `capability_not_in_plan` | AI feature endpoints (`ai`, `studentarea`), not `billing` itself | The caller's current plan/trial doesn't include this AI capability. Bilingual detail (`billing/permissions.py`'s own Arabic default: "هذه الميزة غير متاحة لباقتك الحالية."). |
| `student_cap_reached` | `academics` enrollment create/activate | Adding/activating this student would exceed the plan's/trial's student cap. |
| `renewal_already_in_progress` | *not an HTTP error* — a field in the cancel response (see above), never a status code or `code` value on its own. |

**Not yet a code anywhere in this codebase:** a generic "`entitlement_required`" blanket denial.
Access-not-granted is never a single gate — it is enforced per capability
(`capability_not_in_plan`) and per student-cap action (`student_cap_reached`); billing's own
endpoints (checkout, cancel, status, history) are always reachable regardless of
`access_granted`. If a future unit adds a blanket-denied surface, its code belongs in this table —
do not assume `entitlement_required` is already implemented.

## Entitlement reason codes (`subscription/`'s `entitlement.reason_code`)

| `reason_code` | `access_granted` | Meaning |
|---|---|---|
| `trial_active` | `true` | Within the 16-day trial window. |
| `paid_active` | `true` | A paid period currently covers "now." |
| `cancelled_but_paid_through` | `true` | Cancelled, but still inside the paid-through period. |
| `payment_failed_pending_policy` | `true` | A renewal failed; access is kept pending policy (grace/retry numbers are still an open commercial decision — not yet enforced as a cutoff). |
| `trial_expired` | `false` | Trial window elapsed, no paid period. |
| `period_ended` | `false` | Last paid period elapsed, no new one started. |
| `no_subscription` | `false` | No Subscription row exists for this environment yet. |

## Polling guidance after checkout

There is no push/webhook channel to the Frontend. After redirecting to `session_url`:
1. On return to `checkout/return/?attempt_id=...`, show "pending confirmation."
2. Poll `GET subscription/` (or re-fetch `checkout/return/` with the same `attempt_id`) on a sane
   interval (a few seconds, backing off) until `status` reaches `succeeded` or `failed`/`unknown`
   persists long enough to show a retry prompt. There is no server-defined poll interval or
   timeout; Backend reconciliation (`reconcile_billing_attempts`) resolves `pending`/`unknown`
   attempts on its own schedule, independent of whether the Frontend is still polling.
3. Never fall back to treating "the user is back on our site" as success.

## Trial-days-remaining source

Compute it client-side from `subscription/`'s `trial_end` (already absolute, UTC) minus "now" —
there is no separate "days remaining" field. There is currently **no notification channel** for a
trial-ending reminder (BILL-DEC-06, open); any such reminder is Frontend-side polling/display logic
for now.

## `GET /api/v1/environments/teacher/` stays a list of at most one item

Unrelated to billing's own endpoints, but binding on anything that reads it from the billing pages:
per INV-9, this endpoint remains a **list** response with **at most one item** — never assume a
single-object shape, even though today one teacher has at most one Environment.

## PENDING — restricted-access UI contract (BILL-DEC-02)

What the UI should show/allow when `entitlement.access_granted` is `false` (beyond "billing's own
pages stay open") is **not decided yet**. This section is deliberately left pending rather than
guessed: do not build a "locked state" UI treatment from assumptions. When BILL-DEC-02 resolves,
this section is replaced, not worked around.

## Explicitly out of scope here

Any `apps/web` implementation (Frontend-owned) — including migrating the dead
`apps/web/src/lib/financialsApi.js`, which is flagged here only as something the Frontend owner
should know is unrelated to this module (it is the Student↔Teacher fee tracker, `financials`, not
Kashier billing) and not a reference implementation to copy from.

## Acknowledgement record

| Date | Acknowledged by | Note |
|---|---|---|
| _pending_ | _Frontend owner_ | Hand-off delivered via PR; acknowledgement to be recorded here once received (AC-BILL-032-3). |
