# BILL-WU-040 — Invoice / receipt / tax documents

**ID:** BILL-WU-040 · **Workstream/Package:** BILL-WS-K / BILL-WP-K1
**Status:** OUT OF SCOPE
**Reason:** commercial-model §Open items: "Invoice/receipt/tax requirements — Open"; rejected-deferred: "Commercial-design follow-up / legal". Egypt e-invoicing obligations are unverified (supplementary audit §13).
**Priority / Risk:** — / Medium (possible legal obligation before launch; owner: product + legal)

## Purpose
Tracked placeholder. BILL-WU-008 keeps only an internal "amount owed per period" record (DAT-5
"Invoice / line items where required").

## Expected outcome
None in this plan.

## Requirement / invariant references
DAT-5; commercial-model §Open items.

## Relevant ADRs / contracts
ADR-014.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| Invoice/tax requirements (product + legal) | DECISION / EXTERNAL | Yes, for any future version | Open |

## Preconditions
Not applicable.

## In-scope changes
None.

## Explicit exclusions
Tax computation, invoice numbering sequences, PDF receipts, e-invoicing submission.

## Implementation surfaces (grounded at bf115df)
None.

## Data-integrity & security considerations
Not applicable.

## Failure modes
A legal requirement discovered late could block launch; recorded as BILL-RISK-29.

## Acceptance criteria
- **AC-BILL-040-1:** No tax or invoice-document fields exist in `billing` models (review against BILL-WU-008).

## Verification methods & required evidence
Review.

## Dependencies required before execution
Not planned.

## Completion definition
Remains OUT OF SCOPE until re-scoped.

## Commit boundaries
None.

## Escalation conditions
A legal requirement is confirmed. That becomes a launch gate and must be added to BILL-WU-037.
