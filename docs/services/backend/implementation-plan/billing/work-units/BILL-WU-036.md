# BILL-WU-036 — Kashier sandbox end-to-end verification

**ID:** BILL-WU-036 · **Workstream/Package:** BILL-WS-J / BILL-WP-J2
**Status:** BLOCKED
**Blocked by:** EXTERNAL BILL-EXT-02 (sandbox/test-mode merchant account and test keys) and OPERATIONAL
BILL-OPS-04 (a public HTTPS URL for test-mode webhooks; Kashier rejects localhost and private addresses
per the go-live page, reviewed 2026-10-15).
**Priority / Risk:** P0 / High

## Purpose
Prove the adapter and flows against Kashier's real test mode, turning the BILL-EXT-03 assumptions into
verified facts. This is the step that moves BILL-WU-018/019/020/021/023/025 from IMPLEMENTED to VERIFIED for
their provider-dependent ACs.

## Expected outcome
A recorded sandbox run on staging (or a dedicated public test deployment) that covers: recurring setup
session → hosted card entry with Kashier test cards → setup webhook received and verified → token and
agreement stored → subscription activated (or the confirmed alternative per BILL-EXT-03 if setup doesn't
charge); pay-with-token renewal charge (success and a decline test card) → webhooks verified; duplicate
delivery handling (re-send from the Kashier dashboard if available); status lookup for an attempt; signature
rejection with the wrong key; confirmation of the actual payload fields (`signatureKeys`, token field name,
agreement id) with the BILL-EXT-03 answers recorded in `risks-and-open-issues.md`.

## Requirement / invariant references
ADR-015, ADR-016, ADR-017; commercial-model §External verification context.

## Relevant ADRs / contracts
external-interfaces §Fourth interface.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-EXT-02 | EXTERNAL | Yes | Sandbox account |
| BILL-OPS-04 | OPERATIONAL | Yes | Public webhook URL |
| BILL-WU-018, 019, 020, 021, 023, 025 | BLOCKING | Yes | Things to verify |

## Preconditions
Test keys injected via env (never committed).

## In-scope changes
None to code unless defects are found (each fix gets its own `fix(billing):` commit and regression test).

## Explicit exclusions
Live mode; proving the 30-day interval (sandbox can't prove it; see BILL-WU-026).

## Implementation surfaces (grounded at bf115df)
Deployed staging environment; `apps/backend/billing/*`.

## Data-integrity & security considerations
Test-mode keys only; test cards only; staging DB, not production.

## Failure modes
Docs differ from behaviour (record a deviation, fix the adapter, re-verify).

## Acceptance criteria
- **AC-BILL-036-1:** Each flow listed above is executed with evidence (logs with redaction, DB state snapshots, Kashier dashboard screenshots or exports).
- **AC-BILL-036-2:** BILL-EXT-03 sub-questions answered and recorded.
- **AC-BILL-036-3:** No duplicate application under redelivery.

## Verification methods & required evidence
Sandbox integration run record.

## Dependencies required before execution
BILL-EXT-02, BILL-OPS-04, the listed units.

## Completion definition
AC-1..3 met; dependent units' provider ACs marked VERIFIED.

## Commit boundaries
Only `fix(billing): ...` for defects found.

## Escalation conditions
Kashier behaviour that contradicts ADR-016 assumptions (e.g., no signature on some event types).
