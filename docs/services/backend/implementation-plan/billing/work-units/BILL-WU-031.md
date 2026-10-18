# BILL-WU-031 — Teacher billing API namespace and read endpoints

**ID:** BILL-WU-031 · **Workstream/Package:** BILL-WS-I / BILL-WP-I1
**Status:** READY WITH A TRACKED OPEN ITEM
**Open item:** NODE-WireAPI (`../decisions.md`): serialized schemas, HTTP status choices and the endpoint
catalog are deferred to the API-documentation stage. This unit proposes them and hands them off
(BILL-WU-032); it does not finalize them.
**Priority / Risk:** P1 / Medium

## Purpose
Provide the `/api/v1/billing/` namespace and the read surface listed in AL-4: plan discovery,
subscription/trial status, billing history. These are always reachable, including when access is not granted.

## Expected outcome
`config/urls.py` gains `path("api/v1/billing/", include("billing.urls"))`. Endpoints (indicative):
`GET plans/` (authenticated teachers; global catalog); `GET subscription/` (owner of the active
environment: state, plan, trial end, current period end, cancel flag, entitlement summary from
BILL-WU-010; no internal ids beyond what the client needs); `GET history/` (attempts and periods, paginated
with `StandardPagination`, `environments/tenancy.py:163-172`). All teacher endpoints use
`[IsTeacher, IsEnvironmentMember.for_role("owner")]`. Students get nothing from this namespace. No
provider ids, tokens or raw payloads are exposed.

## Requirement / invariant references
AL-4; ADR-003 (unified API); ADR-008/010; commercial-model §Access-not-granted (billing always reachable).

## Relevant ADRs / contracts
`07-contracts/api-contract.md`; `services/backend/07-contracts/external-api-alignment.md`.

## Dependencies
| Dependency | Type | Blocking? | Why |
|---|---|---|---|
| BILL-WU-008, BILL-WU-009 | BLOCKING / DATA | Yes | Data |
| BILL-WU-010 | CONTRACT | Yes | Entitlement summary |

## Preconditions
None.

## In-scope changes
`billing/urls.py`, read views and serializers, `config/urls.py` include, tests.

## Explicit exclusions
Checkout (BILL-WU-019), cancel (BILL-WU-028) and webhook (BILL-WU-020) endpoints, which mount here but belong to those units; Frontend.

## Implementation surfaces (grounded at bf115df)
`apps/backend/config/urls.py:23-38`; new `apps/backend/billing/{urls.py,views.py,serializers.py}`.

## Data-integrity & security considerations
Field-leak checks similar to `config/test_security_audit.py:267-270` (`test_ai_responses_never_echo_internal_fields`):
the token, agreement id, raw event and merchant secrets are never serialized.

## Failure modes
Leaking another tenant's subscription (header-based tenant tests).

## Acceptance criteria
- **AC-BILL-031-1:** Each read endpoint works for the owning teacher and returns the documented fields.
- **AC-BILL-031-2:** Students, non-owners and cross-tenant requests are refused (`assert_cross_tenant_denied`).
- **AC-BILL-031-3:** No response contains token, agreement, raw payload or provider secret fields.
- **AC-BILL-031-4:** Endpoints are reachable for an environment whose trial has expired.

## Verification methods & required evidence
Integration tests (TenantTestCase).

## Dependencies required before execution
BILL-WU-008, 009, 010.

## Completion definition
AC-1..4 VERIFIED; proposed schema handed to BILL-WU-032.

## Commit boundaries
`feat(billing): add billing API namespace and read endpoints`; `test(billing): cover billing read API scoping`.

## Escalation conditions
A Frontend need that conflicts with server-derived tenant rules.
