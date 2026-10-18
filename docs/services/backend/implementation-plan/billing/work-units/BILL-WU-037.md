# BILL-WU-037 — Staging verification, merchant go-live, production smoke

**ID:** BILL-WU-037 · **Workstream/Package:** BILL-WS-J / BILL-WP-J2
**Status:** BLOCKED
**Blocked by:** EXTERNAL BILL-EXT-04 (live merchant activation: "Merchant <MID> is not live" until onboarding
completes, per Kashier going-live docs reviewed 2026-10-15). Also every launch gate: BILL-WU-007 (prod
cardinality), BILL-WU-013 (restricted ruleset), BILL-WU-015 (legacy backfill), BILL-WU-016 (repeat-trial
decision), BILL-WU-026 (30-day gate), BILL-WU-027 (scheduler), BILL-WU-030 (retry/grace), BILL-WU-033
(notifications), BILL-WU-036 (sandbox).
**Priority / Risk:** P0 / Critical

## Purpose
Launch billing in production safely and prove it with a smoke test.

## Expected outcome
1. **Staging verification:** full regression suite green; BILL-WU-034 green; three billing workers
   scheduled (BILL-WU-027); a complete test-mode lifecycle on staging (signup → trial → checkout →
   activation → renewal → cancel → end).
2. **Go-live checklist (from Kashier docs; confirm at execution):** live account activated; live Payment
   API Key and Secret Key injected (keys are mode-specific); live base URLs; egress IP allow-list updated if
   used; live-mode webhook created separately on a public HTTPS URL with exact event subscription; redirect
   and webhook verification uses the live Payment API Key; payment methods enabled on the live account.
3. **Production smoke (per Kashier's smoke list):** one small live transaction by an internal teacher
   account. The order reaches the expected status, confirmed via **order reconciliation, not the browser
   redirect**. Webhook received and verified. Subscription activated with a 30-day period. Refund of that
   transaction: Kashier recommends it, but Madar refunds are OUT OF SCOPE (BILL-WU-038), so a manual
   dashboard refund by Operations is recorded as an operational step, not a Madar feature. Transaction
   appears in a settlement window.
4. Production migrations applied (BILL-WU-007, billing migrations) and backfill run (BILL-WU-015).

## Requirement / invariant references
commercial-model §External verification context (going live); OP-PARITY; all billing requirements.

## Relevant ADRs / contracts
ADR-014..018.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-EXT-04 | EXTERNAL | Yes | Live merchant |
| BILL-WU-007, 013, 015, 016, 026, 027, 030, 033, 036 | BLOCKING / DECISION | Yes | Launch gates |
| BILL-WU-034, 035 | VERIFICATION | Yes | Security and observability in place |

## Preconditions
Go/no-go meeting record naming the approver.

## In-scope changes
Configuration and deployment only.

## Explicit exclusions
Building refunds.

## Implementation surfaces (grounded at bf115df)
Deployment (Operations); `apps/backend/config/settings.py` env values.

## Data-integrity & security considerations
Live keys only in production secret storage; never in staging.

## Failure modes
Smoke failure (roll back by disabling `PAYMENT_PROVIDER=kashier` live checkout and renewal flags; data retained).

## Acceptance criteria
- **AC-BILL-037-1:** Staging lifecycle record complete.
- **AC-BILL-037-2:** Go-live checklist items each ticked with evidence.
- **AC-BILL-037-3:** Production smoke steps each evidenced; status confirmed through reconciliation, not redirect.
- **AC-BILL-037-4:** All listed launch-gate units are VERIFIED or explicitly waived by a named approver (a waiver is recorded as risk acceptance, never silent).

## Verification methods & required evidence
Ops records; reconciliation output; go/no-go record.

## Dependencies required before execution
All listed.

## Completion definition
AC-1..4 met. The plan can then be marked COMPLETE.

## Commit boundaries
None (operations).

## Escalation conditions
Any gate unresolved at the planned launch date.
