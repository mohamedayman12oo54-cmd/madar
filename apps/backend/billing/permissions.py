"""
BILL-WU-011 — the permission-layer boundary where Billing's entitlement
contract (BILL-WU-010) is actually consulted (ADR-018; ai-execution-
guidance directive 8): entitlement checks run as a DRF permission, listed
**after** `IsEnvironmentMember` in `permission_classes`, never inside
`accounts/authentication.py`.

`RequiresCapability(capability)` is a factory — not a class — because each
call must bind its own capability key as a closure; `permission_classes`
entries are instantiated fresh per request (`[p() for p in
permission_classes]`), so the returned class carries that binding the same
way `IsEnvironmentMember.for_role(...)` (`environments/tenancy.py:125-127`)
carries a bound role.

Reads `request.environment` directly, never via `getattr(..., None)`: if
`IsEnvironmentMember` was left off (or listed after this permission) there
is no `request.environment` yet, and this must fail loudly with an
`AttributeError` (mirrors `TenantScopedQuerySetMixin`,
`environments/tenancy.py:136-139`) rather than silently granting or
denying access. An automated test (`billing/test_entitlement_enforcement.py`,
AC-BILL-011-5) asserts the correct ordering on every decorated view instead.

This never reads a tenant from the request body or query string, and never
leaks cross-tenant state: `IsEnvironmentMember` (listed first) already
raises `EnvironmentForbidden` for a mismatched/foreign environment before
this permission is ever evaluated.
"""
from rest_framework import exceptions
from rest_framework.permissions import BasePermission

from . import entitlements


class CapabilityNotInPlan(exceptions.PermissionDenied):
    """PROPOSED status/code (NODE-WireAPI hasn't finalized this — same
    caveat as BILL-WU-031's proposed response shapes): 403, matching
    `environments.tenancy.EnvironmentForbidden`'s choice for "authenticated,
    tenant-resolved, but not allowed to do this.\""""

    default_detail = "هذه الميزة غير متاحة لباقتك الحالية."
    default_code = "capability_not_in_plan"


class RequiresCapabilityBase(BasePermission):
    """Common base every `RequiresCapability(...)` call's returned class
    inherits from — lets `test_entitlement_enforcement.py`'s ordering check
    recognize any bound instance via `issubclass(cls, RequiresCapabilityBase)`
    without caring which capability it was bound to."""

    required_capability = None

    def has_permission(self, request, view):
        decision = entitlements.decide(request.environment)
        if self.required_capability not in decision.capabilities:
            raise CapabilityNotInPlan()
        return True


def RequiresCapability(capability):
    """Returns a `RequiresCapabilityBase` subclass bound to `capability`,
    for direct use in a view's `permission_classes` list, e.g.:

        permission_classes = [IsTeacher, IsEnvironmentMember.for_role("owner"),
                               RequiresCapability(capabilities.AI_PERFORMANCE_ANALYSIS)]
    """
    return type(
        f"RequiresCapability_{capability.replace('.', '_')}",
        (RequiresCapabilityBase,),
        {"required_capability": capability},
    )
