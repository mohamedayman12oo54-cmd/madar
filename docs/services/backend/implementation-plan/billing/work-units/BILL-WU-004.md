# BILL-WU-004 — Duplicate-owner remediation (conditional, approval-gated)

**ID:** BILL-WU-004 · **Workstream/Package:** BILL-WS-A / BILL-WP-A2
**Status:** BLOCKED
**Blocked by:** DATA (BILL-WU-003 per-DB results) + DECISION (BILL-DEC-01 remediation policy)
**Priority / Risk:** P0 / High (destructive-data risk)

## Purpose
If BILL-WU-003 finds owners with more than one Environment in any target DB, bring that DB into
compliance with INV-9 **only** through an explicitly approved, per-database policy. This unit
deliberately prescribes **no** cleanup method. Merging, deleting or re-parenting Environments destroys
or reassigns tenant data (Enrollments, payments, AI history, notifications), and the access-not-granted
principle ("Teacher Account and its data must never be destroyed") applies in spirit.

## Expected outcome
For each DB with duplicates, an approved written policy is applied and the DB passes BILL-WU-003 with
zero duplicates. If BILL-WU-003 reports zero duplicates in every target DB, this unit closes as **N/A**
with that evidence.

Candidate options for BILL-DEC-01 (to be **decided by the data owner/product, not by the implementer**):
(a) **reseed** non-production DBs from scratch after BILL-WU-005 fixes `seed_demo`. This is likely
sufficient for dev DBs seeded by `seed_demo`. (b) **Split ownership:** create a new Teacher Account for
each extra Environment and transfer `owner` plus the owner membership. This needs a new identity
(email/phone are `unique=True`, `accounts/models.py:50-51`) and teacher consent. (c) **Archive** the
extra environments by some mechanism. None exists today, and inventing one would need its own
decision. (d) **Manual case-by-case** handling with the affected teacher. Option (e), deleting or merging
without approval, is **prohibited**.

## Requirement / invariant references
INV-9; ADR-013 §Consequences; commercial-model §Access-not-granted principle (data never destroyed); `06-data/lifecycle-retention.md` (indefinite retention, no deletion workflow).

## Relevant ADRs / contracts
ADR-013; ADR-004/007 (tenant data integrity).

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-003 (AC-6 per DB) | DATA | Yes | Need the facts first |
| BILL-DEC-01 | DECISION | Yes | Remediation policy must be approved per DB |
| BILL-WU-005 (seed fix) | BLOCKING for option (a) | Conditional | Reseeding must not recreate duplicates |
| Verified backup/PITR of the target DB | OPERATIONAL | Yes | `09-operations/backup-recovery.md` |

## Preconditions
Approved policy document naming the DB, the affected owner ids, the chosen option and the approver.
Fresh backup confirmed restorable.

## In-scope changes
Executing the approved policy, preferably as a reviewed, idempotent, dry-run-capable script or data
migration scoped to named owner ids. Re-running BILL-WU-003.

## Explicit exclusions
Any remediation without BILL-DEC-01 approval. Any generic "keep newest, delete rest" logic. Any change
to production data before staging rehearsal.

## Implementation surfaces (grounded at bf115df)
Depends on the option chosen. Likely `apps/backend/environments/` (data migration or one-off command).
`seed_demo.py:39-46` for option (a).

## Data-integrity & security considerations
Every tenant-scoped row (all `TenantOwnedModel` subclasses with `environment` FK, `environments/tenancy.py:149-161`)
is affected by any re-parenting. Dry-run output must be reviewed. Audit-log who approved and ran it.

## Failure modes
Data loss (mitigated by approval, backup and dry-run); a partial run (must be transactional per owner);
teacher confusion after a split (communication is a product responsibility).

## Acceptance criteria
- **AC-BILL-004-1:** For every target DB, either the BILL-WU-003 report shows zero duplicates (unit closes N/A) or an approved BILL-DEC-01 policy record exists for that DB.
- **AC-BILL-004-2:** After remediation, BILL-WU-003 reports zero duplicates and zero incoherent memberships for that DB.
- **AC-BILL-004-3:** Row counts of tenant-scoped tables before and after match what the approved policy predicts (no unexpected deletion).

## Verification methods & required evidence
Before/after BILL-WU-003 reports; approval record; dry-run log; row-count diff.

## Dependencies required before execution
BILL-WU-003 (AC-6), BILL-DEC-01, backup confirmation.

## Completion definition
All target DBs compliant with evidence, or N/A recorded.

## Commit boundaries
If code is needed: `fix(environments): add approved remediation for duplicate environment owners` (scoped, reviewed). No commit for reseed-only.

## Escalation conditions
Any duplicate in production; any remediation option that needs a new mechanism (archive, account
split UX); any doubt about consent. Escalate to product/data owner. Do not proceed.
