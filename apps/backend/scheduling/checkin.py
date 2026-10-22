"""
Session self check-in — a student marks THEMSELVES present by scanning the
teacher's QR, then entering their platform phone number and the code the
teacher announced.

Security model (all enforced here, never by the client):

* Two secrets, two channels. The QR carries an opaque token; the six-digit code
  is told to the room. Possessing the QR (e.g. a photo sent to a friend who is
  not in class) is not enough.
* Scope: the link belongs to ONE session of ONE environment. The phone must be
  an ACTIVE member of that session's group, so a student of another teacher (or
  another group) can neither check in nor learn anything.
* Power: the ONLY thing this can do is write `present`. It never writes
  absence, recitation or payments, never reads a record, and never overwrites
  an absence the teacher marked by hand.
* No oracle: every identity failure (unknown phone, wrong code, not in the
  group, inactive) returns the same message. The code is compared in constant
  time.
* Brute force: throttled per IP, per phone and per link (the latter caps the
  whole 10^6 code space for the link's whole lifetime).
"""
import hmac

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import generics, serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from accounts.serializers import clean_phone
from accounts.throttles import CheckinIPRateThrottle, CheckinLinkRateThrottle, CheckinPhoneRateThrottle
from environments.tenancy import IsEnvironmentMember

from .models import CheckinLink, SessionInstance
from .services import (
    GENERIC_CHECKIN_FAILURE, active_checkin_link, issue_checkin_link, revoke_checkin_links, self_check_in,
)

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
INVALID_LINK = "هذا الرمز غير صالح أو انتهت صلاحيته. اطلب من المعلّم رمزًا جديدًا."


def _link_payload(link):
    return {
        "token": link.token,
        "code": link.code,
        "expires_at": link.expires_at,
        "checked_in_count": link.checked_in_count,
    }


# ------------------------------------------------------------------ teacher --
class SessionCheckinView(APIView):
    """GET current link (or null) · POST create/regenerate · DELETE revoke."""

    permission_classes = IS_ENV_OWNER

    def _session(self, request, pk):
        return generics.get_object_or_404(
            SessionInstance.objects.filter(environment=request.environment).select_related("group"), pk=pk)

    def get(self, request, pk):
        session = self._session(request, pk)
        link = active_checkin_link(session)
        return Response({"link": _link_payload(link) if link else None})

    def post(self, request, pk):
        session = self._session(request, pk)
        try:
            link = issue_checkin_link(session)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": list(exc.messages)})
        return Response({"link": _link_payload(link)}, status=status.HTTP_201_CREATED)

    def delete(self, request, pk):
        revoke_checkin_links(self._session(request, pk))
        return Response(status=status.HTTP_204_NO_CONTENT)


# ------------------------------------------------------------------- public --
def _usable_link(token):
    link = (CheckinLink.objects.select_related("session__group", "environment")
            .filter(token=(token or "")[:64]).first())
    if link is None:
        return None
    session = link.session
    if session.is_overdue():
        session.close(auto=True)
    return link if link.is_usable() else None


class CheckinInfoView(APIView):
    """What the check-in form shows before the student types anything: only the
    environment, group and time - nothing about who is enrolled."""

    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [CheckinIPRateThrottle]

    def get(self, request, token):
        link = _usable_link(token)
        if link is None:
            return Response({"detail": INVALID_LINK, "code": "checkin_invalid"}, status=status.HTTP_404_NOT_FOUND)
        session = link.session
        return Response({
            "environment": link.environment.name,
            "group": session.group.name,
            "scheduled_at": session.scheduled_at,
        })


class CheckinSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=40)
    code = serializers.CharField(max_length=12)

    def validate_phone(self, value):
        return clean_phone(value)

    def validate_code(self, value):
        # Accept Arabic-Indic digits too (students type on Arabic keyboards).
        trans = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")
        digits = "".join(ch for ch in value.translate(trans) if ch.isdigit())
        if len(digits) != 6:
            raise serializers.ValidationError("الكود مكوّن من ٦ أرقام.")
        return digits


class CheckinSubmitView(CheckinInfoView):
    throttle_classes = [CheckinIPRateThrottle, CheckinPhoneRateThrottle, CheckinLinkRateThrottle]

    def post(self, request, token):
        ser = CheckinSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        link = _usable_link(token)
        if link is None:
            return Response({"detail": INVALID_LINK, "code": "checkin_invalid"}, status=status.HTTP_404_NOT_FOUND)
        if not hmac.compare_digest(link.code.encode(), ser.validated_data["code"].encode()):
            raise serializers.ValidationError({"detail": [GENERIC_CHECKIN_FAILURE]})
        try:
            outcome, enrollment = self_check_in(link, ser.validated_data["phone"])
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": list(exc.messages)})
        return Response({
            "result": outcome,
            "name": enrollment.display_name,
            "group": link.session.group.name,
            "environment": link.environment.name,
        })
