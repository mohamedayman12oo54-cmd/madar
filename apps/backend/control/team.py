"""The team's own accounts, roles and permissions.

Escalation rules (enforced here, on the server):
  * nobody changes their OWN role, permissions or active state;
  * nobody can hand out a permission they do not hold themselves;
  * only a super admin can touch another super admin;
  * the last active super admin can never be demoted or deactivated.
Team accounts are NOT created here: they are provisioned through the existing backend command
(`create_team_user`), never through a public or in-app signup."""
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

from accounts.models import User
from accounts.session_revocation import revoke_all_sessions

from . import audit
from .access import HasControlPerm, effective_permissions, perms_of, role_key
from .common import ControlView, invalid, iso
from .models import Role, TeamProfile, Ticket
from .permissions_catalog import GROUP_LABELS, PERMISSIONS


class MeView(ControlView):
    """What the signed-in team member may do — the frontend builds its menu from this, the server never does."""

    perm = ()

    def get_permissions(self):
        from rest_framework.permissions import IsAuthenticated

        return [IsAuthenticated()]

    def get(self, request):
        u = request.user
        if u.role != "team":
            raise PermissionDenied("هذه المنطقة لفريق مدار فقط.")
        profile = getattr(u, "team_profile", None)
        return Response({
            "id": u.id, "name": u.name, "role": profile.role.key if profile else None,
            "role_name": profile.role.name if profile else "مدير المحتوى (قديم)",
            "permissions": sorted(effective_permissions(u)),
        })


class PermissionCatalogView(ControlView):
    perm = ("roles.view", "team.view")

    def get(self, request):
        groups = {}
        for key, (group, label) in PERMISSIONS.items():
            groups.setdefault(group, {"key": group, "label": GROUP_LABELS[group], "permissions": []})["permissions"].append(
                {"key": key, "label": label})
        return Response(list(groups.values()))


# ------------------------------------------------------------------ members
def member_json(u, detail=False):
    p = getattr(u, "team_profile", None)
    perms = effective_permissions(u) if u.is_active else set()
    d = {
        "id": u.id, "name": u.name, "username": u.username, "email": u.email, "is_active": u.is_active,
        "role": p.role.key if p else None, "role_name": p.role.name if p else "بدون دور (قاعدة المعرفة فقط)",
        "permission_count": len(perms), "last_login": iso(u.last_login), "date_joined": iso(u.date_joined),
        "assigned_active": Ticket.objects.filter(assignee=u, status__in=Ticket.ACTIVE).count(),
        "resolved": Ticket.objects.filter(assignee=u, status__in=("resolved", "closed")).count(),
    }
    if detail:
        d.update(permissions=sorted(perms), extra_permissions=p.extra_permissions if p else [],
                 revoked_permissions=p.revoked_permissions if p else [])
    return d


class MemberListView(ControlView):
    perm = "team.view"

    def get(self, request):
        qs = User.objects.filter(role="team").select_related("team_profile__role").order_by("name", "id")
        if s := request.query_params.get("search", "").strip()[:100]:
            qs = qs.filter(Q(name__icontains=s) | Q(username__icontains=s) | Q(email__icontains=s))
        return Response([member_json(u) for u in qs])


def _member(pk):
    return get_object_or_404(User.objects.filter(role="team").select_related("team_profile__role"), pk=pk)


def _active_super_admins():
    return User.objects.filter(role="team", is_active=True, team_profile__role__key="super_admin")


class _MemberEdit(serializers.Serializer):
    name = serializers.CharField(max_length=150, required=False)
    role = serializers.SlugField(required=False)
    is_active = serializers.BooleanField(required=False)
    extra_permissions = serializers.ListField(child=serializers.CharField(), required=False, max_length=60)
    revoked_permissions = serializers.ListField(child=serializers.CharField(), required=False, max_length=60)

    def validate_name(self, v):
        v = v.strip()
        if len(v) < 2:
            raise serializers.ValidationError("الاسم يجب ألا يقل عن حرفين.")
        return v

    def _known(self, v):
        bad = [p for p in v if p not in PERMISSIONS]
        if bad:
            raise serializers.ValidationError(f"صلاحيات غير معروفة: {', '.join(bad)}")
        return sorted(set(v))

    validate_extra_permissions = _known
    validate_revoked_permissions = _known


class MemberDetailView(ControlView):
    def get_permissions(self):
        return [HasControlPerm.require("team.manage" if self.request.method == "PATCH" else "team.view")()]

    def get(self, request, pk):
        return Response(member_json(_member(pk), detail=True))

    def patch(self, request, pk):
        ser = _MemberEdit(data=request.data, partial=True)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        mine = perms_of(request)
        i_am_super = role_key(request.user) == "super_admin"
        with transaction.atomic():
            target = get_object_or_404(User.objects.select_for_update().filter(role="team"), pk=pk)
            profile = TeamProfile.objects.select_related("role").filter(user=target).first()
            privileged = {"role", "is_active", "extra_permissions", "revoked_permissions"} & set(d)
            if privileged and target.pk == request.user.pk:
                raise PermissionDenied("لا يمكنك تعديل دورك أو صلاحياتك أو حالتك بنفسك.")
            if profile and profile.role.key == "super_admin" and not i_am_super and privileged:
                raise PermissionDenied("لا يعدّل حساب المدير العام إلا مدير عام.")
            before, after = {}, {}

            if "name" in d and d["name"] != target.name:
                before["name"], after["name"] = target.name, d["name"]
                target.name = d["name"]
                target.save(update_fields=["name"])

            if "role" in d:
                role = Role.objects.filter(key=d["role"]).first()
                if not role:
                    raise invalid(role="دور غير معروف.")
                if not i_am_super and not set(role.permissions) <= mine:
                    raise PermissionDenied("لا يمكنك منح دور يحتوي صلاحيات لا تملكها.")
                if (profile.role.key if profile else None) == "super_admin" and role.key != "super_admin" \
                        and target.is_active and _active_super_admins().count() <= 1:
                    raise invalid(role="لا يمكن إزالة آخر مدير عام.")
                if profile is None:
                    profile = TeamProfile.objects.create(user=target, role=role)
                    before["role"], after["role"] = None, role.key
                elif profile.role_id != role.id:
                    before["role"], after["role"] = profile.role.key, role.key
                    profile.role = role
                    profile.save(update_fields=["role", "updated_at"])

            for field in ("extra_permissions", "revoked_permissions"):
                if field in d:
                    if profile is None:
                        raise invalid(**{field: "عيّن دورًا للعضو أولًا."})
                    if field == "extra_permissions" and not i_am_super and not set(d[field]) <= mine:
                        raise PermissionDenied("لا يمكنك منح صلاحيات لا تملكها.")
                    old = getattr(profile, field)
                    if sorted(old) != d[field]:
                        before[field], after[field] = old, d[field]
                        setattr(profile, field, d[field])
                        profile.save(update_fields=[field, "updated_at"])

            if "is_active" in d and d["is_active"] != target.is_active:
                if not d["is_active"] and profile and profile.role.key == "super_admin" and _active_super_admins().count() <= 1:
                    raise invalid(is_active="لا يمكن تعطيل آخر مدير عام.")
                before["is_active"], after["is_active"] = target.is_active, d["is_active"]
                target.is_active = d["is_active"]
                target.save(update_fields=["is_active"])
                if not target.is_active:
                    revoke_all_sessions(target)  # a deactivated member is signed out of every device immediately

            if after:
                action = "team.deactivate" if after.get("is_active") is False else \
                    "team.activate" if after.get("is_active") else \
                    "team.role" if "role" in after else \
                    "team.permissions" if ({"extra_permissions", "revoked_permissions"} & set(after)) else "team.update"
                audit.record(request, action, "team_member", target.id, target.name, before, after)
        return Response(member_json(_member(pk), detail=True))


class MemberTicketsView(ControlView):
    perm = ("team.view", "tickets.view")

    def get(self, request, pk):
        from .support import ticket_row

        m = _member(pk)
        qs = Ticket.objects.filter(assignee=m).select_related("category", "assignee")
        return Response([ticket_row(t) for t in qs.order_by("-last_activity_at")[:50]])


class MemberActivityView(ControlView):
    perm = ("team.view", "audit.view")

    def get(self, request, pk):
        from .models import AuditLog
        from .users import audit_row

        m = _member(pk)
        return Response([audit_row(a) for a in AuditLog.objects.filter(actor=m)[:60]])


# ------------------------------------------------------------------ roles
def role_json(r):
    return {"id": r.id, "key": r.key, "name": r.name, "description": r.description, "permissions": r.permissions,
            "is_system": r.is_system, "members": r.members.count(), "locked": r.key == "super_admin"}


class _RoleWrite(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    description = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    permissions = serializers.ListField(child=serializers.CharField(), max_length=60)

    def validate_permissions(self, v):
        bad = [p for p in v if p not in PERMISSIONS]
        if bad:
            raise serializers.ValidationError(f"صلاحيات غير معروفة: {', '.join(bad)}")
        return sorted(set(v))


class RoleListCreateView(ControlView):
    def get_permissions(self):
        return [HasControlPerm.require("roles.manage" if self.request.method == "POST" else "roles.view")()]

    def get(self, request):
        return Response([role_json(r) for r in Role.objects.all()])

    def post(self, request):
        ser = _RoleWrite(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        _check_grantable(request, d["permissions"])
        import re
        from django.utils.text import slugify

        base = re.sub(r"[^a-z0-9_-]", "", slugify(d["name"], allow_unicode=False).replace("-", "_")) or "role"
        key, n = base, 1
        while Role.objects.filter(key=key).exists():
            n += 1
            key = f"{base}_{n}"
        r = Role.objects.create(key=key[:40], name=d["name"].strip(), description=d["description"], permissions=d["permissions"])
        audit.record(request, "role.create", "role", r.id, r.name, after={"permissions": r.permissions})
        return Response(role_json(r), status=201)


def _check_grantable(request, perms):
    if role_key(request.user) != "super_admin" and not set(perms) <= perms_of(request):
        raise PermissionDenied("لا يمكنك منح صلاحيات لا تملكها.")


class RoleDetailView(ControlView):
    perm = "roles.manage"

    def patch(self, request, pk):
        r = get_object_or_404(Role, pk=pk)
        if r.key == "super_admin":
            raise PermissionDenied("دور المدير العام لا يُعدَّل.")
        ser = _RoleWrite(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        _check_grantable(request, d["permissions"])
        if r.key in {role_key(request.user)} and set(r.permissions) - set(d["permissions"]):
            raise PermissionDenied("لا يمكنك سحب صلاحيات من دورك أنت.")
        before = {"name": r.name, "permissions": r.permissions}
        r.name, r.description, r.permissions = d["name"].strip(), d["description"], d["permissions"]
        r.save()
        audit.record(request, "role.update", "role", r.id, r.name, before, {"name": r.name, "permissions": r.permissions})
        return Response(role_json(r))

    def delete(self, request, pk):
        r = get_object_or_404(Role, pk=pk)
        if r.is_system:
            raise PermissionDenied("الأدوار الأساسية لا تُحذف.")
        if r.members.exists():
            raise invalid(detail="لا يمكن حذف دور له أعضاء. انقل الأعضاء إلى دور آخر أولًا.")
        audit.record(request, "role.delete", "role", r.id, r.name)
        r.delete()
        return Response(status=204)
