"""
Student self-registration by QR.

Teacher side (owner of the environment): GET the current link, POST to create/regenerate it (the old one
stops working at once), DELETE to switch registration off.

Public side (no login): GET shows ONLY what the form needs (the teacher's space name and its grades with
their groups); POST enrols the student through the SAME serializer the teacher's "add student" form uses,
so every rule (one group, grade/group match, phone validity, plan cap) applies identically.

Security model, enforced here and never by the client:
* The token is an unguessable bearer secret with an expiry and an instant revoke.
* Power: the only thing it can do is create an Enrollment in its own environment. It cannot read a roster.
* The student's badge code is NEVER returned: it is the second proof of the activation flow and is handed
  over by the teacher. Registering therefore does not let a stranger activate an account.
* No oracle: an already-enrolled phone and a fresh one get the identical success response, and a phone that
  belongs to a non-student account gets a generic refusal.
* Abuse: throttled per IP, per phone and per link.
"""
from types import SimpleNamespace

from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from accounts.throttles import RegisterIPRateThrottle, RegisterLinkRateThrottle, RegisterPhoneRateThrottle
from billing.entitlements import StudentCapReached
from environments.tenancy import IsEnvironmentMember

from .models import Enrollment, Grade, Group, RegistrationLink
from .serializers import NOT_ADDABLE, EnrollmentCreateSerializer

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
INVALID_LINK = "رابط التسجيل غير صالح أو انتهت صلاحيته. اطلب من المعلّم رابطًا جديدًا."
CANNOT_REGISTER = "تعذّر التسجيل بهذه البيانات. تواصل مع المعلّم."
CLOSED = "التسجيل مغلق حاليًا. تواصل مع المعلّم."
DONE = "تم تسجيلك بنجاح. سيعطيك المعلّم كود الطالب الخاص بك لاحقًا."


def active_link(environment):
    link = RegistrationLink.objects.filter(environment=environment, revoked_at__isnull=True).first()
    return link if link and link.is_usable() else None


def issue_link(environment):
    with transaction.atomic():
        now = timezone.now()
        RegistrationLink.objects.filter(environment=environment, revoked_at__isnull=True).update(revoked_at=now)
        return RegistrationLink.objects.create(environment=environment, expires_at=now + RegistrationLink.VALID_FOR)


def _payload(link):
    return {"token": link.token, "expires_at": link.expires_at, "registered_count": link.registered_count}


# ------------------------------------------------------------------ teacher --
class RegistrationLinkView(APIView):
    permission_classes = IS_ENV_OWNER

    def get(self, request):
        link = active_link(request.environment)
        return Response({"link": _payload(link) if link else None})

    def post(self, request):
        return Response({"link": _payload(issue_link(request.environment))}, status=status.HTTP_201_CREATED)

    def delete(self, request):
        RegistrationLink.objects.filter(environment=request.environment, revoked_at__isnull=True).update(
            revoked_at=timezone.now())
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------- public --
def _usable(token):
    link = RegistrationLink.objects.select_related("environment").filter(token=(token or "")[:64]).first()
    return link if link and link.is_usable() else None


def _invalid():
    return Response({"detail": INVALID_LINK, "code": "registration_invalid"}, status=status.HTTP_404_NOT_FOUND)


class RegistrationInfoView(APIView):
    """What the public form shows before anything is typed: the space's name and its grades/groups."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [RegisterIPRateThrottle]

    def get(self, request, token):
        link = _usable(token)
        if link is None:
            return _invalid()
        env = link.environment
        groups = {}
        for g in Group.objects.filter(environment=env).order_by("name"):
            groups.setdefault(g.grade_id, []).append({"id": g.id, "name": g.name})
        grades = [
            {"id": gr.id, "name": gr.name, "groups": groups.get(gr.id, [])}
            for gr in Grade.objects.filter(environment=env).order_by("id")
        ]
        return Response({"environment": env.name, "grades": grades})


class PublicRegistrationSerializer(EnrollmentCreateSerializer):
    """The teacher's add-student rules, with the public form's shape: ONE group (required), guardian name
    and phone required, and the new student always active."""

    group_id = serializers.IntegerField()
    group_ids = None
    is_active = None
    parent_name = serializers.CharField(max_length=150, required=True, allow_blank=False)

    def validate(self, attrs):
        attrs["group_ids"] = [attrs.pop("group_id")]
        attrs["is_active"] = True
        return super().validate(attrs)


class RegistrationSubmitView(RegistrationInfoView):
    throttle_classes = [RegisterIPRateThrottle, RegisterPhoneRateThrottle, RegisterLinkRateThrottle]

    def post(self, request, token):
        link = _usable(token)
        if link is None:
            return _invalid()
        ctx = {"request": SimpleNamespace(environment=link.environment)}
        ser = PublicRegistrationSerializer(data=request.data, context=ctx)
        try:
            ser.is_valid(raise_exception=True)
        except serializers.ValidationError as exc:
            # A phone that belongs to a non-student account must not be revealed to the public.
            phone_errors = exc.detail.get("phone") if isinstance(exc.detail, dict) else None
            if phone_errors and any(str(e) == str(NOT_ADDABLE) for e in phone_errors):
                raise serializers.ValidationError({"detail": CANNOT_REGISTER})
            raise
        try:
            enrollment, created = ser.save()
        except StudentCapReached:
            return Response({"detail": CLOSED, "code": "registration_closed"}, status=status.HTTP_409_CONFLICT)
        if created:
            RegistrationLink.objects.filter(pk=link.pk).update(registered_count=F("registered_count") + 1)
        # Same body whether the phone was new or already enrolled here: no roster oracle, and the badge
        # code is deliberately not included.
        return Response({"detail": DONE}, status=status.HTTP_201_CREATED)
