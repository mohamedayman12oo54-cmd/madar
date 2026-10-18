# Traceability Matrix — BILL-PLAN-01

> Bidirectional: Source (requirement / invariant / ADR / contract / risk) → Work Unit → Acceptance Criteria →
> Verification evidence. Evidence types are defined in `verification-plan.md` §4. Gaps are flagged in §5;
> they are not hidden.

## 1. Forward trace — requirements and invariants

| Source | Statement (abridged) | WU(s) | Key ACs | Evidence |
|---|---|---|---|---|
| functional §Billing b1 / commercial-model §Plans | Exactly three plans, fixed prices/caps/features; no extra tier, annual billing or discount | 009, 019, 011, 012 | AC-BILL-009-1/2, AC-BILL-019-1/2, AC-BILL-011-1, AC-BILL-012-1 | tests |
| functional §Billing b2 / commercial-model §Free trial | 16-day trial at the Backend-authoritative activation + environment instant; Plan 3 features; cap 250; no card; no auto-convert | 014, 010, 012 | AC-BILL-014-1..6, AC-BILL-010-1/5, AC-BILL-012-1 | tests |
| commercial-model §Free trial (repeat-trial open) | Not decided | 016 (BLOCKED) | AC-BILL-016-1 | decision record |
| functional §Billing b3 / commercial-model §Billing period | Exactly 30 elapsed days; never calendar month | 024, 025, 021 | AC-BILL-024-1..4, AC-BILL-025-1, AC-BILL-021-1 | tests |
| commercial-model §Auto-renewal | Auto-renew for subscriptions on a recurring agreement | 018, 019, 021, 025, 026 | AC-BILL-021-1 (agreement stored), AC-BILL-025-1, AC-BILL-026-1..3 | tests; sandbox; Kashier answer; prod first cycle |
| commercial-model §Cancellation | Effective at end of paid period; stops the next renewal only; no implied refund | 028, 025, 010 | AC-BILL-028-1..6, AC-BILL-025-5, AC-BILL-010-3 | tests |
| functional §Billing b4 / commercial-model §Failed renewal | No termination on single failure; limited retries; notification; grace; reconcile ambiguous before re-charge | 029, 023, 025, 030 (BLOCKED), 033 (BLOCKED) | AC-BILL-029-1..4, AC-BILL-023-1/2, AC-BILL-025-3/4, AC-BILL-030-*, AC-BILL-033-1 | tests; pending decisions |
| functional §Billing b5 / commercial-model §Access-not-granted | Never destroy account/data; keep auth, billing and export; Backend-enforced gating | 010, 011, 013 (BLOCKED), 031, 004 | AC-BILL-010-6, AC-BILL-011-3, AC-BILL-013-2/3, AC-BILL-031-4, AC-BILL-004-3 | tests; approval records |
| functional §Billing b6 / ADR-014 / BND-4 | Dedicated `billing` module distinct from `financials` | 001, 008 | AC-BILL-001-1/2, AC-BILL-008-7 | boot check; static test |
| commercial-model §Commercial ownership unit | Account → one Environment → that Environment's Subscription | 006, 008, 014 | AC-BILL-006-2, AC-BILL-008-1, AC-BILL-014-1 | tests |
| **INV-9** / ADR-013 | One Teacher Account owns exactly one Environment, permanently; DB-level enforcement; live-data check; fixture update | 003, 004, 005, 006, 007 | AC-BILL-003-1..6, AC-BILL-004-1..3, AC-BILL-005-1..4, AC-BILL-006-1..7, AC-BILL-007-1..3 | tests; per-DB ops records |
| ADR-015 (concerns 1-5) | Madar-owned interface, separate shape from VideoProvider; adapter; inbound verify+translate; transitions only from verified output | 017, 018, 020, 021 | AC-BILL-017-1/6, AC-BILL-018-1..6, AC-BILL-020-3, AC-BILL-021-5 | tests; sandbox |
| ADR-016 prerequisites + trust distinctions | Signature verification; correlation; idempotent processing; redirect ≠ proof; only webhook or reconciliation transitions state; no other inbound | 019, 020, 021, 023, 034 | AC-BILL-019-3, AC-BILL-020-1..7, AC-BILL-021-2/5, AC-BILL-023-1, AC-BILL-034-2 | tests; sandbox |
| ADR-017 separations | Provider-event dedup ≠ AI client idempotency; attempt / amount-owed / subscription / entitlement separate; reconciliation | 008, 020, 021, 023, 029 | AC-BILL-008-2/3, AC-BILL-020-2/5, AC-BILL-021-2/3, AC-BILL-023-*, AC-BILL-029-2 | tests |
| ADR-018 / TAL-5 / security-authz caution | Billing-owned contract; consumed after tenant/authz resolution; not in `get_user()`; Backend-enforced; Worker parity | 010, 011, 012 | AC-BILL-010-7, AC-BILL-011-4/5/6/7 | tests; static checks |
| DAT-5 | Candidate logical concepts (Plan, Subscription, BillingPeriod, Invoice where required, PaymentAttempt, agreement ref, provider event, derived entitlement) | 008, 009, 010 | AC-BILL-008-1..8 | tests |
| AL-3 | Payment trust-boundary distinctions | 019, 020, 021 | as ADR-016 | tests |
| AL-4 | Frontend contract needs | 031, 032, 019, 028, 012, 011 | AC-BILL-031-*, AC-BILL-032-1..4 | review, acknowledgment |
| OP-PARITY / EX-1 / EX-3 | Worker gets no weaker guarantees | 011, 022, 023, 025 | AC-BILL-011-6, AC-BILL-022-2, AC-BILL-025-2 | tests |
| external-interfaces §Fourth interface / §Negative space | Payment provider via Billing only; sole inbound exception | 017, 020, 034 | AC-BILL-017-1, AC-BILL-020-6, AC-BILL-034-2 | tests |
| configuration-secrets | No hard-coded secrets; none in logs | 017, 035 | AC-BILL-017-5, AC-BILL-035-1 | tests |
| commercial-model §External verification (Kashier) | Webhook contract from Kashier docs; go-live verification; 30-day gate | 018, 020, 026, 036, 037 | AC-BILL-018-6, AC-BILL-026-1, AC-BILL-036-1..3, AC-BILL-037-2/3 | sandbox; Kashier answer; ops |
| commercial-model §Open items (refund, proration, invoice/tax, AI quotas, price change) | Open, not built | 038, 039, 040, 041, 042 (OUT OF SCOPE) | AC-BILL-038-1 … 042-1 (scope guards) | review |

## 2. Forward trace — risks

| Risk | Mitigating WU(s) | AC | Covered? |
|---|---|---|---|
| BILL-RISK-01 | 001, 002 | AC-BILL-001-1, 002-1 | Yes |
| BILL-RISK-02 | 001 | AC-BILL-001-3 | Yes |
| BILL-RISK-03 | 003, 004, 005, 007 | AC-BILL-003-6, 004-1, 005-4, 007-1 | Yes |
| BILL-RISK-04 | 026 (gate), 018 | AC-BILL-026-1, 018-4 | Yes (as gate) |
| BILL-RISK-05 | 020, 034, 019 | AC-BILL-020-6, 034-2, 019-3 | Yes |
| BILL-RISK-06 | 029, 030 | AC-BILL-029-3, 030-1 | Partial (030 BLOCKED) |
| BILL-RISK-07 | 013, 010 | AC-BILL-013-2, 010-6 | Partial (013 BLOCKED; export gap G-01) |
| BILL-RISK-08 | 016 | AC-BILL-016-1 | Partial (BLOCKED) |
| BILL-RISK-09 | 041 (OUT OF SCOPE) | AC-BILL-041-1 | **No mitigation, flagged U-01** |
| BILL-RISK-10 | 027, 002 (manual evidence) | AC-BILL-027-1..3 | Partial; CI not addressed (U-02) |
| BILL-RISK-11 | 033 | AC-BILL-033-1 | Partial (BLOCKED) |
| BILL-RISK-12 | 032, 019 | AC-BILL-032-2, 019-3 | Yes |
| BILL-RISK-13 | 037, 017 | AC-BILL-037-2, 017-4 | Yes (as gate) |
| BILL-RISK-14 | 009, 011 | AC-BILL-009-3, 011-8 | Partial (decision) |
| BILL-RISK-15 | 015 | AC-BILL-015-1 | Partial (BLOCKED) |
| BILL-RISK-16 | 020 | AC-BILL-020-5 | Yes |
| BILL-RISK-17 | 022, 025 | AC-BILL-022-2, 025-2/3 | Yes |
| BILL-RISK-18 | 020, 021 | AC-BILL-020-1/2/7 | Yes |
| BILL-RISK-19 | 018, 036 | AC-BILL-018-6, 036-2 | Yes (via sandbox) |
| BILL-RISK-20 | 036, 021 | AC-BILL-036-2 | Yes (via sandbox) |
| BILL-RISK-21 | 018 | review | Yes |
| BILL-RISK-22 | 002 | AC-BILL-002-1 | Yes |
| BILL-RISK-23 | 024, 010 | AC-BILL-024-1, 010-1 | Yes |
| BILL-RISK-24 | `ai-execution-guidance.md` directive | — | Informational, no WU (U-03) |
| BILL-RISK-25 | — | — | Informational, no WU (U-03) |
| BILL-RISK-26 | 012 | AC-BILL-012-5 | Partial (decision) |
| BILL-RISK-27 | 003 (reporting only) | AC-BILL-003-3 | Partial (reported, not enforced) |
| BILL-RISK-28 | 028, 025 | AC-BILL-028-2..4 | Yes |
| BILL-RISK-29 | 040 (OUT OF SCOPE) | AC-BILL-040-1 | **No mitigation, flagged U-04** |
| BILL-RISK-30 | 037 runbook, 021 (refund events stored) | AC-BILL-021-8 | Partial |
| BILL-RISK-31 | 039 (OUT OF SCOPE) | AC-BILL-039-1 | Accepted limitation |
| BILL-RISK-32 | 019, 032 | — (no AC until BILL-EXT-05 answers) | Partial (U-05) |

## 3. Reverse trace — every WU to its justification

| WU | Justified by |
|---|---|
| 001 | ADR-014; BILL-RISK-01 |
| 002 | Implemented ≠ Verified principle (`../verification.md`); BILL-RISK-10/22 |
| 003-007 | INV-9; ADR-013 §Consequences |
| 008 | DAT-5; ADR-017 |
| 009 | commercial-model §Plans |
| 010 | ADR-018; TAL-5 |
| 011 | ADR-018; OP-PARITY |
| 012 | commercial-model caps; AL-4 |
| 013 | commercial-model §Access-not-granted |
| 014 | commercial-model §Free trial |
| 015 | BILL-RISK-15 (no doc requirement; see §5 O-01) |
| 016 | commercial-model §Free trial (open item) |
| 017, 018 | ADR-015 |
| 019 | ADR-016; AL-4 |
| 020 | ADR-016 |
| 021, 022 | ADR-016/017 |
| 023 | ADR-017 §Reconciliation; commercial-model §Failed renewal |
| 024, 025 | commercial-model §Billing period, §Auto-renewal |
| 026 | commercial-model §Open items (launch/design gate) |
| 027 | operations.md §Routed follow-ups; commercial-model §Open items |
| 028 | commercial-model §Cancellation |
| 029, 030 | commercial-model §Failed renewal |
| 031, 032 | AL-4 |
| 033 | commercial-model §Failed renewal (notification) |
| 034 | ADR-016/017/018; INV-7 |
| 035 | ADR-014 (traceability records); configuration-secrets |
| 036, 037 | commercial-model §External verification (going live) |
| 038-042 | commercial-model §Open items |

Every WU has a source. **No orphan task**, though see O-01.

## 4. Coverage summary

- Billing functional requirements (6 bullets): 6/6 traced to ≥ 1 WU. 4/6 fully verifiable now; b4 and b5 are
  partially blocked (030, 033, 013).
- Invariants: INV-9 fully traced. INV-7 regression-traced via 034 and §10 of the verification plan.
- ADR-013..018: 6/6 traced with ACs.
- Risks (32, tallied from §2): **16** fully covered (01, 02, 03, 04, 05, 12, 13, 16, 17, 18, 19, 20, 21, 22,
  23, 28); **11** partial (06, 07, 08, 10, 11, 14, 15, 26, 27, 30, 32); **1** accepted limitation (31); **2**
  with no mitigating WU (09, 29 → U-01, U-04); **2** informational with no WU (24, 25 → U-03).
  16 + 11 + 1 + 2 + 2 = 32.

## 5. Flagged gaps (not hidden)

| ID | Kind | Gap | Where tracked |
|---|---|---|---|
| G-01 | Orphan requirement (implementation) | The access-not-granted principle requires an "appropriate path to review/export their own data". **No export capability exists** in the codebase, and only BLOCKED BILL-WU-013 addresses it | BILL-RISK-07, BILL-DEC-02 |
| G-02 | Orphan requirement (blocked) | "Clear notification to the teacher plus recovery instructions" has no channel (BILL-WU-033 BLOCKED) | BILL-RISK-11 |
| G-03 | **Orphan requirement** | Plan 3 "separately-priced future feature" identification mechanism (commercial-model §Plan 3) has **no WU** (its mechanism is Open) | commercial-model §Open items |
| G-04 | Orphan requirement (feature) | Plan 2 "AI chat about video-lesson content" has no implementation and no WU builds it. This plan only defines the capability key | BILL-RISK-14, BILL-DEC-07 |
| O-01 | Task justified by risk, not requirement | BILL-WU-015 (legacy backfill) has no documentary requirement; it needs BILL-DEC-03 | BILL-RISK-15 |
| U-01 | Uncovered risk | AI usage cost (BILL-RISK-09) | OUT OF SCOPE 041 |
| U-02 | Uncovered risk | Absence of CI (part of BILL-RISK-10) | Recommendation only |
| U-03 | Uncovered (informational) | BILL-RISK-24/25 | AI guidance note |
| U-04 | Uncovered risk | Invoice/tax legal (BILL-RISK-29) | OUT OF SCOPE 040 |
| U-05 | Unverified quality constraint | Recurring-agreement consent compliance has no AC until BILL-EXT-05 answers | BILL-RISK-32 |
| U-06 | Unverified quality constraint | The production 30-elapsed-day cadence can't be verified before BILL-EXT-01, and sandbox can't prove it | BILL-WU-026 |
| U-07 | Unverified quality constraint | No numeric availability or latency target exists for webhook ack beyond Kashier's 30 s timeout. AC-BILL-020-1 asserts in-request receipt only, with no performance test | BILL-RISK-18 |
