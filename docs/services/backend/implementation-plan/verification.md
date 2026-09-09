# Verification Model — Outcome → Acceptance Criteria → Method → Evidence

> **Authority:** Layer 4 (derived). Verifies the **documented boundary/guarantee**, never an invented
> mechanism. **Implemented ≠ Verified** — a WU is not complete until its outcome is demonstrated.
> AC below are seeds; concrete acceptance tests are authored at implementation time from these seeds.

## Verification methods (vocabulary)

unit · integration · contract · **isolation negative-suite** (attempted cross-tenant access) ·
failure-injection · crash/replay · idempotency · property/all-paths · regression · perf-smoke · ops verification.
Evidence = test results, CI result, review record, spike report, ops record.

## Guarantee-critical verification (depth raised by risk model)

| WU | Acceptance-criteria seed | Method | Evidence |
|---|---|---|---|
| FND-03 (spike) → FND-04 | No cross-tenant access on any path (web + worker) | isolation negative-suite + property/all-paths | spike report, CI |
| FND-05 | Client-supplied tenant refused; context server-derived; switch only to authorized envs | integration + negative | CI |
| FND-06 / SE-03 | Authz fails on missing actor/role/env/relationship; Teacher Private Notes never student-visible | unit + integration + negative | CI |
| FND-07 | Invariant/business-rule violation → business-rule/conflict, no partial/silent write | unit + integration + negative | CI |
| FND-08 (spike) → FND-09/10, EO-04 | Record + event atomic (no lost-event window); at-least-once; idempotent consumer; crash/replay safe | integration + crash/replay + idempotency | spike report, CI |
| RUN-01 | No delivery/AI/batch on sync path; per-tap durable; close = transition; qualitative bar 40–50/group mid-range | integration + perf-smoke | CI |
| RUN-02 / AI-02 / AI-03 | submit→poll→terminal; failure → no partial; idempotent submit; AI non-authoritative | integration + failure-injection + idempotency | CI |
| IE-03 | INV-1/2/3/4/6: one Enrollment per (Student×Env×Year); immutable Grade; membership within Grade | unit + integration + negative | CI |
| FIN-02 | Fee via Grade (INV-5); second Group same Grade → no extra obligation | unit + integration + negative | CI |
| AUTH-01 | Claiming reaches existing identity; no new identity/rebuild | integration + regression | CI |

## Lifecycle-seam verification (boundary only — no invented mechanism)

| WU | Acceptance-criteria seed | Method | Evidence |
|---|---|---|---|
| TAL-01 | Capability request refused without an authenticated Teacher actor context; actor distinct from student; **no auth mechanism assumed** | contract + integration + regression | CI |
| TAL-02 | Established Environment begins **empty**; isolation holds from origin; **trigger/cardinality not asserted** | integration + isolation negative-test | CI |
| TAL-03 | Introduction enters the existing claiming model unchanged; **no new identity/account** | regression + contract | CI |
| TAL-04 | Access-state consulted as an input, separate from & prior to composite authz; **no billing, no access-not-granted behavior asserted, no `default-open`** | contract + integration | CI |

## Module verification (AC-seeds carried from Stage 7; method summary)

IE-01/02/05 · EO-01/02/03/05 · FIN-01 · SE-01/02/04 · CON-01/02/03 · AI-01 · NOT-01/02 · API-01 · EXT-01/02/03 ·
OPS-01/02 — each has an AC-seed (see `work-breakdown.md`) and a valid path, typically unit + integration + contract;
fenced portions (🏭 vendor / 📄 serialized schema / 🚧 ownership) are verified at the **seam** now and completed when the
governing decision resolves.

## Regression-critical suite (guards the documentation delta)

A dedicated suite confirms the Teacher-lifecycle additions did **not** change existing truth:
- Student identity/claiming behavior preserved (teacher-created → unclaimed → phone-based claim → authenticated).
- Composite authorization model unchanged; access-state is an input *alongside*, not inside.
- Tenant isolation + `teacher_environment_id` semantics unchanged (web + worker).
- All ADRs and student fee tracking unchanged; Teacher commercial access ≠ student fee tracking.

## Coverage / orphan checks

- Every meaningful WU (49/49) has a verification path. ✅
- Every AC-seed has a WU target; no verification orphan. ✅
- **Implemented ≠ Verified** preserved: SEAM-READY WUs are not declared verified for their fenced mechanism portion.
- Verification-ordering (spikes → consumers; seams → FND-05/API-01) is distinguished from execution prerequisites.

## Gate

Stage 10 verification model is complete and coherent. Verification is planned *alongside* implementation for
every wave; each gate requires verified (not merely implemented) outcomes at the documented boundary.
