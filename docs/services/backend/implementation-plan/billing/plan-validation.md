# Plan Validation — BILL-PLAN-01

> **Overall plan status: DRAFT.** The artifacts are complete and internally consistent, and that is all
> this status asserts. 11 units are BLOCKED on named decisions or external facts, including the launch
> gate BILL-EXT-01. The baseline itself (BILL-RISK-01) is probably unbootable. **No tests were executed while
> authoring this plan.** Validation date 2026-10-15, baseline `bf115df`.

## 1. Acceptance-criteria checklist

### 1.1 Scope integrity

| Check | Result | Evidence |
|---|---|---|
| Every in-scope area maps to ≥ 1 WU | PASS | `scope.md` §1 S-01..S-15 → WU column |
| Out-of-scope items are explicit and tracked | PASS | `scope.md` §2; WU-038..042 OUT OF SCOPE |
| No Frontend implementation planned | PASS | Only BILL-WU-032 (hand-off); `apps/web` excluded everywhere |
| `financials` untouched and not conflated | PASS | Exclusions in units; AC-BILL-008-7 |
| No open commercial number defaulted | PASS | 010/025/029 exclude retry/grace; 030 BLOCKED; 016 BLOCKED; 038-042 OUT OF SCOPE; directive 4 |
| ADR-016 exception not broadened | PASS | AC-BILL-020-6, AC-BILL-034-2; directive 9 |

**Category: PASS.**

### 1.2 Architecture integrity

| Check | Result | Evidence |
|---|---|---|
| ADR-013..018 respected; no ADR-019+/amendments exist | PASS | `README.md` baseline; units cite ADRs |
| Entitlement not placed in `MadarJWTAuthentication.get_user()`; Environment/membership resolved first | PASS | BILL-WU-011 §Expected outcome 1-2; AC-BILL-011-4/5/7 |
| Provider boundary follows ADR-009 shape, not `VideoProvider` | PASS | BILL-WU-017; AC-BILL-017-6 |
| Provider-event integrity separate from AI `idempotency_key` | PASS | BILL-WU-020; AC-BILL-020-5 |
| Worker pattern within existing Web/Worker split; no broker | PASS | BILL-WU-022/023/025 |
| Module boundaries (BND-1/4) | PASS | Capability calls in 011, 012, 014 |
| Baseline drift recorded, not silently fixed | PASS | BILL-RISK-01/02/03/24/25 |
| Physical schema not over-mandated beyond DAT-5/INV-9 | PASS | BILL-WU-008 (guarantees mandatory, names free) |

**Category: PASS.**

### 1.3 Dependency integrity

| Check | Result | Evidence |
|---|---|---|
| Every WU's dependencies are typed (8-type vocabulary) | PASS | Per-unit tables; `dependency-graph.md` §1-2 |
| Graph acyclic | PASS | Kahn sort over 42 nodes / 99 edges completed |
| Apparent cycles explained and resolved | PASS | `dependency-graph.md` §4 (four cases) |
| Unit files and the edge table are consistent | PASS (after correction) | Two inconsistencies were found during validation and fixed: BILL-WU-022 had listed 027 as a prerequisite (reversed edge), and BILL-WU-013 listed a non-edge to 032 |
| Sequencing derived from the graph, deviations explained | PASS | `dependency-graph.md` §5 |
| External gate kept external | PASS | BILL-EXT-01 → 026 BLOCKED; not resolved by doc reading |

**Category: PASS.**

### 1.4 Traceability integrity

| Check | Result | Evidence |
|---|---|---|
| Requirements → WU → AC → evidence | PASS | `traceability-matrix.md` §1 |
| Risks → WU | PARTIAL | 16 full, 11 partial, 1 accepted, 2 unmitigated (09, 29), 2 informational (§2, §4) |
| Every WU justified (no orphan task) | PASS, with one flag | §3; O-01 (BILL-WU-015 justified by risk only) |
| Orphan requirements flagged | PARTIAL (gaps exist and are disclosed) | G-01 export path, G-02 notifications, G-03 Plan 3 future-feature mechanism, G-04 Plan 2 chat feature |

**Category: PARTIAL.** Traceability is complete and honest, but it surfaces real requirement gaps.

### 1.5 Verification integrity

| Check | Result | Evidence |
|---|---|---|
| Every WU has stable-ID ACs (171 AC bullets over 42 files) | PASS | literal grep count |
| Every AC has a method and evidence | PASS | `verification-plan.md` §4 |
| Authored vs executed vs sandbox vs staging vs prod distinguished | PASS | `verification-plan.md` §3 |
| Tests executed during authoring | **None** (stated) | — |
| Unverifiable constraints disclosed | PARTIAL | U-05, U-06, U-07; the 30-day interval can't be verified before BILL-EXT-01 |
| Verification environment available | **FAIL at baseline** | BILL-RISK-01 (phantom app) and BILL-RISK-22 (Postgres needed); no CI (BILL-RISK-10) |

**Category: PARTIAL.** The plan is sound, but the environment can't currently execute it.

### 1.6 Execution integrity

| Check | Result | Evidence |
|---|---|---|
| Every unit has implementation surfaces grounded in real paths at `bf115df` | PASS | 42/42 files contain the section; paths were checked by reading code |
| Commit boundaries follow observed style | PASS | `git log --oneline -30`: `feat(scope):`, `test(scope):`, `docs(scope):`, `build(scope):`, `style(scope):` |
| Escalation conditions per unit | PASS | 42/42 |
| High-risk units fully specified (cardinality, persistence, trial, entitlement, provider, webhook, renewal, cancellation, failure) | PASS | 003-007, 008, 010, 011, 014, 017-021, 025, 026, 028, 029 |
| End-to-end executable today | **FAIL** | 11 BLOCKED, including the launch gates; the root unit's verification needs BILL-OPS-02 |

**Category: PARTIAL.**

### Summary

| Category | Result |
|---|---|
| Scope integrity | PASS |
| Architecture integrity | PASS |
| Dependency integrity | PASS |
| Traceability integrity | PARTIAL |
| Verification integrity | PARTIAL |
| Execution integrity | PARTIAL |

## 2. Literal Work Unit enumeration (from `work-units/`, 42 files)

| WU | Status | WP |
|---|---|---|
| 001 | READY WITH A TRACKED OPEN ITEM | A1 |
| 002 | READY | A1 |
| 003 | READY | A2 |
| 004 | BLOCKED | A2 |
| 005 | READY | A2 |
| 006 | READY | A2 |
| 007 | BLOCKED | A2 |
| 008 | READY WITH A TRACKED OPEN ITEM | B1 |
| 009 | READY WITH A TRACKED OPEN ITEM | B1 |
| 010 | READY WITH A TRACKED OPEN ITEM | C1 |
| 011 | READY WITH A TRACKED OPEN ITEM | C2 |
| 012 | READY WITH A TRACKED OPEN ITEM | C2 |
| 013 | BLOCKED | C2 |
| 014 | READY | D1 |
| 015 | BLOCKED | D1 |
| 016 | BLOCKED | D1 |
| 017 | READY | E1 |
| 018 | READY WITH A TRACKED OPEN ITEM | E1 |
| 019 | READY WITH A TRACKED OPEN ITEM | E2 |
| 020 | READY WITH A TRACKED OPEN ITEM | F1 |
| 021 | READY WITH A TRACKED OPEN ITEM | F2 |
| 022 | READY | F2 |
| 023 | READY WITH A TRACKED OPEN ITEM | F2 |
| 024 | READY | G1 |
| 025 | READY WITH A TRACKED OPEN ITEM | G1 |
| 026 | BLOCKED | G2 |
| 027 | BLOCKED | G2 |
| 028 | READY WITH A TRACKED OPEN ITEM | H1 |
| 029 | READY WITH A TRACKED OPEN ITEM | H1 |
| 030 | BLOCKED | H1 |
| 031 | READY WITH A TRACKED OPEN ITEM | I1 |
| 032 | READY WITH A TRACKED OPEN ITEM | I1 |
| 033 | BLOCKED | I2 |
| 034 | READY | J1 |
| 035 | READY WITH A TRACKED OPEN ITEM | J1 |
| 036 | BLOCKED | J2 |
| 037 | BLOCKED | J2 |
| 038 | OUT OF SCOPE | K1 |
| 039 | OUT OF SCOPE | K1 |
| 040 | OUT OF SCOPE | K1 |
| 041 | OUT OF SCOPE | K1 |
| 042 | OUT OF SCOPE | K1 |

**Tally (counted from the table, and cross-checked with `grep '^**Status:**'` over the 42 files):**

| Status | Count | Units |
|---|---|---|
| READY | **9** | 002, 003, 005, 006, 014, 017, 022, 024, 034 |
| READY WITH A TRACKED OPEN ITEM | **17** | 001, 008, 009, 010, 011, 012, 018, 019, 020, 021, 023, 025, 028, 029, 031, 032, 035 |
| BLOCKED | **11** | 004, 007, 013, 015, 016, 026, 027, 030, 033, 036, 037 |
| OUT OF SCOPE | **5** | 038, 039, 040, 041, 042 |
| **Total** | **42** | 9 + 17 + 11 + 5 = 42 ✔ |

Work Packages: **18** distinct (A1, A2, B1, C1, C2, D1, E1, E2, F1, F2, G1, G2, H1, I1, I2, J1, J2, K1).
Workstreams: **11** (A–K).

## 3. Critical execution path

`BILL-WU-001 → 008 → 009 → 010 → 031 → 019 → 021 → 023 → 025 → 028 → 033 → 037`
(12 units over execution-blocking edges; equal-length branch `025 → 036 → 026 → 037`).
Gates on the path: BILL-DEC-06 (033), BILL-EXT-02 (036), BILL-EXT-01 (026), BILL-EXT-04 (037); feeding 037:
BILL-DEC-01/03/04/05/02 via 004/007, 015, 016, 030, 013; BILL-OPS-01 via 027.

## 4. Blocking items by unit

| Unit | Blocked by |
|---|---|
| 004 | DATA: per-DB BILL-WU-003 result + DECISION BILL-DEC-01 |
| 007 | DATA: zero-duplicate report per DB (and 004 if needed) |
| 013 | BILL-DEC-02 |
| 015 | BILL-DEC-03 |
| 016 | BILL-DEC-04 |
| 026 | **BILL-EXT-01** (Kashier exact 30-elapsed-day compatibility) + BILL-WU-027 + BILL-WU-036 + BILL-EXT-04 |
| 027 | BILL-OPS-01 |
| 030 | BILL-DEC-05 (+ BILL-DEC-02) |
| 033 | BILL-DEC-06 |
| 036 | BILL-EXT-02 + BILL-OPS-04 |
| 037 | BILL-EXT-04 + units 007, 013, 015, 016, 026, 027, 030, 033, 036 |

## 5. Limitations of this validation

- Static reading only. No code executed, no DB queried (so BILL-RISK-01's boot failure and BILL-RISK-03's live
  duplicates are inferences), no migrations run.
- Kashier facts come from public docs on one date. Only sandbox and written confirmation make them binding.
- The brief's "Section 9.9" and "Section 10" texts were not available verbatim. Directives and the
  illustrative-order comparison are adapted (see `ai-execution-guidance.md` and `dependency-graph.md` §5).
- `config/test_security_audit.py` was inspected for structure (class and test list), not every assertion.
- Line numbers are as of `bf115df` and will drift.

## 6. Readiness statement

The plan stays **DRAFT**. It may move to **IN EXECUTION** once BILL-WU-001 is VERIFIED and BILL-OPS-02 is
satisfied. It may be declared **READY (fully executable)** only when every BLOCKED unit has its gate resolved
or formally deferred by a named owner. **BILL-EXT-01 is the gate that decides whether production renewal is
possible at all.**
