"""Backend enforcement of the Control Center's permissions. The frontend hides menu entries by the same list,
but nothing here trusts it: every control endpoint declares the permission it needs and this class checks it
against the database on every request."""
from rest_framework.permissions import BasePermission

from .permissions_catalog import ALL, LEGACY_PERMISSIONS, PERMISSIONS


def effective_permissions(user) -> set:
    """The permissions a team account holds right now. Non-team accounts and inactive accounts hold none."""
    if not (user and getattr(user, "is_authenticated", False) and getattr(user, "role", None) == "team"
            and user.is_active):
        return set()
    profile = getattr(user, "team_profile", None)
    if profile is None:
        return set(LEGACY_PERMISSIONS)
    role = profile.role
    if role.key == "super_admin":
        return set(ALL)
    perms = set(role.permissions or [])
    perms |= set(profile.extra_permissions or [])
    perms -= set(profile.revoked_permissions or [])
    return {p for p in perms if p in PERMISSIONS}


def has_perm(user, key) -> bool:
    return key in effective_permissions(user)


def role_key(user):
    profile = getattr(user, "team_profile", None)
    return profile.role.key if profile else None


class HasControlPerm(BasePermission):
    """`permission_classes = [HasControlPerm.require("users.view")]`. Several keys = ANY of them is enough."""

    required = ()
    message = "ليس لديك صلاحية تنفيذ هذا الإجراء."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        mine = effective_permissions(request.user)
        request.control_permissions = mine
        return any(k in mine for k in self.required)

    @classmethod
    def require(cls, *keys):
        for k in keys:
            if k not in PERMISSIONS:
                raise ValueError(f"unknown permission {k}")
        return type("Needs_" + "_".join(k.replace(".", "_") for k in keys), (cls,), {"required": tuple(keys)})


def perms_of(request) -> set:
    cached = getattr(request, "control_permissions", None)
    if cached is None:
        cached = request.control_permissions = effective_permissions(request.user)
    return cached


def can(request, key) -> bool:
    return key in perms_of(request)
