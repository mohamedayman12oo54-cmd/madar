"""
Tenant (Teacher Environment) context resolution — Phase 1 foundation.

THE RULE THIS FILE ENFORCES: the tenant is never whatever the client claims
it is. A request names the environment it wants to act in through exactly
one channel — the `X-Madar-Environment` header — and this module is the only
place that reads it. Every other place `environment_id` might appear in a
request (URL kwarg, query string, JSON body) is domain input, not
authorization, and must never be used to decide *which* environment a
request is scoped to. Views that need a tenant-scoped queryset or want to
stamp `environment` on a new row use `request.environment`, which is only
ever set here, only after checking `EnvironmentMembership`.

This module has no models of its own (`TenantOwnedModel` is an abstract base
meant to be inherited by Phase 2+ domain models such as Grade/Group/Session
— it adds no table itself) and needs no new Django app or migration.

Usage in a Phase 2+ view::

    class GroupViewSet(TenantScopedQuerySetMixin, viewsets.ModelViewSet):
        permission_classes = [IsTeacher, IsEnvironmentMember]
        queryset = Group.objects.all()
        serializer_class = GroupSerializer

`IsEnvironmentMember` resolves and validates the header and sets
`request.environment` / `request.environment_membership` *before* the view
runs; `TenantScopedQuerySetMixin` then filters `get_queryset()` by it and
stamps it onto anything the view creates.
"""
from django.db import models
from rest_framework import exceptions
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission

from .models import Environment, EnvironmentMembership

# The one and only channel a request may use to name its tenant. Django
# exposes a header "X-Madar-Environment" as request.META["HTTP_X_MADAR_ENVIRONMENT"].
ACTIVE_ENVIRONMENT_HEADER = "X-Madar-Environment"
_META_KEY = "HTTP_" + ACTIVE_ENVIRONMENT_HEADER.upper().replace("-", "_")


class EnvironmentRequired(exceptions.APIException):
    """No (or a malformed) X-Madar-Environment header. This is a client
    precondition failure, not an authorization failure — 400, not 403 — so
    it's distinguishable from "you asked for a real environment you don't
    belong to" (EnvironmentForbidden, below)."""

    status_code = 400
    default_detail = "يجب تحديد بيئة العمل عبر ترويسة X-Madar-Environment."
    default_code = "environment_required"


class EnvironmentForbidden(exceptions.PermissionDenied):
    """The header named a real-looking environment id, but the authenticated
    user has no membership in it. Deliberately worded identically whether
    the id belongs to another teacher, doesn't exist at all, or exists but
    the user was removed from it — never confirms or denies that a given id
    is a real environment (no enumeration signal)."""

    default_detail = "غير مصرح لك بالوصول إلى هذه البيئة."
    default_code = "environment_forbidden"


def resolve_environment(request):
    """Read + validate the active-environment header for `request.user`.

    Returns the EnvironmentMembership row (not just the Environment) so
    callers can see the caller's role in it. Raises EnvironmentRequired /
    EnvironmentForbidden rather than returning None, so every call site
    gets the same error shape for free.
    """
    raw = request.META.get(_META_KEY)
    if raw is None or not str(raw).strip():
        raise EnvironmentRequired()
    try:
        environment_id = int(str(raw).strip())
    except (TypeError, ValueError):
        raise EnvironmentRequired()

    membership = (
        EnvironmentMembership.objects.filter(environment_id=environment_id, user=request.user)
        .select_related("environment", "environment__owner")
        .first()
    )
    if membership is None:
        raise EnvironmentForbidden()
    return membership


class IsEnvironmentMember(BasePermission):
    """Attach to any view whose queryset/writes must be scoped to one
    Teacher Environment. On success, sets:

      request.environment             -> Environment instance
      request.environment_membership  -> EnvironmentMembership instance (has .role)

    Optionally restrict to one membership role:
        permission_classes = [IsEnvironmentMember]                  # any member
        permission_classes = [IsEnvironmentMember.for_role("owner")] # owner only
    """

    required_role = None

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            raise exceptions.NotAuthenticated()
        membership = resolve_environment(request)
        role = self.required_role or getattr(view, "required_environment_role", None)
        if role is not None and membership.role != role:
            raise EnvironmentForbidden()
        request.environment = membership.environment
        request.environment_membership = membership
        return True

    @classmethod
    def for_role(cls, role):
        return type(f"IsEnvironmentMember_{role}", (cls,), {"required_role": role})


class TenantScopedQuerySetMixin:
    """Mixin for DRF generic views/viewsets whose model has an `environment`
    FK. Combine with IsEnvironmentMember (which must run first, i.e. be
    listed before any other permission that touches the queryset) so
    `request.environment` is already set.

    Deliberately does NOT catch the AttributeError if `IsEnvironmentMember`
    was left off permission_classes — that must fail loudly in development,
    not silently return an unscoped (cross-tenant) queryset.
    """

    def get_queryset(self):
        qs = super().get_queryset()
        return qs.filter(environment=self.request.environment)

    def perform_create(self, serializer):
        serializer.save(environment=self.request.environment)


class TenantOwnedModel(models.Model):
    """Abstract base for Phase 2+ domain models scoped to a Teacher
    Environment (Grade, Group, Session Instance, Payment, ...). Adds no
    table by itself. `related_name="+"` is overridden per concrete model by
    Django automatically via the subclass's own app_label/model name, so two
    subclasses never collide on Environment's reverse accessor.
    """

    environment = models.ForeignKey(Environment, on_delete=models.CASCADE, related_name="+")

    class Meta:
        abstract = True


class StandardPagination(PageNumberPagination):
    """Default pagination for Phase 2+ list endpoints. Not applied to the
    existing teacher/student environment lists (bounded by how many
    environments one person can own/join — pagination there would only add
    an unnecessary envelope around a handful of items and is a breaking
    response-shape change those screens don't need)."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100
