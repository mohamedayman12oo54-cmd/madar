"""
Teacher QR scanner — scan a student's badge, then act.

Security model (every point is enforced server-side, never by the client):

* The badge carries an OPAQUE token (`Enrollment.qr_token`), not an id and not
  any personal data. Photographing a badge reveals nothing, and ids cannot be
  enumerated by incrementing a number.
* Resolution is ALWAYS scoped to the caller's active environment, so a badge
  belonging to another teacher's student does not resolve at all (404) — the
  response is identical to an unknown token, so the scanner cannot be used to
  probe whether a badge exists elsewhere.
* The caller must be the environment owner, and the session must belong to the
  same environment and be OPEN before anything is recorded.
* Every action is an UPSERT on an existing uniqueness constraint
  (session+enrollment for attendance/recitation, enrollment+month for
  payments), so a double scan corrects in place instead of creating a second
  record. Repeating a scan is therefore safe; an intentional change still
  overwrites.
* Writes reuse the SAME services/validation as the manual screens
  (`mark_attendance`, `mark_recitation`), so the scanner cannot become a path
  that bypasses a domain rule.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment
from accounts.permissions import IsTeacher
from accounts.throttles import ScanRateThrottle
from config.months import current_month
from environments.tenancy import IsEnvironmentMember
from financials.models import MonthlyPayment

from .models import AttendanceRecord, GuestVisit, RecitationRecord, SessionInstance
from .services import is_member, mark_attendance, mark_guest, mark_recitation


def _record(fn, session, enrollment, status_value):
    """Domain rules (session must be OPEN; the enrollment must belong to the
    session's group) raise Django's ValidationError. Surface them as a 400
    exactly like the manual screens, never a 500 — and never bypass them."""
    try:
        fn(session, enrollment, status_value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"detail": list(exc.messages)})

def _record_any(kind, session, enrollment, status_value):
    """Badge scanned at a session of ANOTHER group: record it as a guest visit
    (carried into his own group's session when that opens) instead of failing.
    Same-group scans go through the unchanged manual-screen services."""
    if enrollment.environment_id == session.environment_id and not is_member(session, enrollment):
        try:
            mark_guest(session, enrollment, kind, status_value)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"detail": list(exc.messages)})
        return
    _record(mark_attendance if kind == "attendance" else mark_recitation, session, enrollment, status_value)


IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]


def _enrollment_for(request, token):
    """Badge code -> Enrollment, strictly inside the caller's environment.

    The alphabet is uppercase-only, so a hand-typed lowercase code is accepted
    by normalising first. Spaces and dashes a teacher might add for
    readability are stripped too. This loses no entropy — those characters
    were never part of an issued code.
    """
    code = (token or "").strip().replace(" ", "").replace("-", "").upper()
    return generics.get_object_or_404(
        Enrollment.objects.filter(environment=request.environment).select_related("grade"),
        qr_token=code,
    )


def _session_for(request, session_id):
    return generics.get_object_or_404(
        SessionInstance.objects.filter(environment=request.environment), pk=session_id
    )


def _snapshot(enrollment, session):
    """What the scanner shows after a scan: who this is, and what has already
    been recorded — so the teacher can see a repeat scan is a no-op."""
    month = current_month()
    attendance = AttendanceRecord.objects.filter(session=session, enrollment=enrollment).first() if session else None
    recitation = RecitationRecord.objects.filter(session=session, enrollment=enrollment).first() if session else None
    visit = GuestVisit.objects.filter(session=session, enrollment=enrollment).select_related("home_session__group").first() if session else None
    payment = MonthlyPayment.objects.filter(enrollment=enrollment, month=month).first()
    return {
        "enrollment_id": enrollment.id,
        "name": enrollment.display_name,
        "grade": enrollment.grade.name,
        "is_active": enrollment.is_active,
        "session_id": session.id if session else None,
        "attendance": attendance.status if attendance else (visit.attendance or None if visit else None),
        "recitation": recitation.status if recitation else (visit.recitation or None if visit else None),
        "guest": ({"home_session": ({"id": visit.home_session_id, "scheduled_at": visit.home_session.scheduled_at,
                                     "group": visit.home_session.group.name} if visit.home_session_id else None)}
                  if visit else None),
        "month": month.strftime("%Y-%m"),
        "fee_amount": str(enrollment.grade.fee_amount),
        "payment_status": payment.status if payment else MonthlyPayment.Status.UNPAID,
    }


class ScanSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=64)
    session_id = serializers.IntegerField(required=False, allow_null=True)


class ScanResolveView(APIView):
    """POST a scanned token -> who it is + what is already recorded.
    Records nothing: the teacher picks the action next."""

    permission_classes = IS_ENV_OWNER
    throttle_classes = [ScanRateThrottle]

    def post(self, request):
        ser = ScanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        enrollment = _enrollment_for(request, ser.validated_data["token"])
        session = _session_for(request, ser.validated_data["session_id"]) if ser.validated_data.get("session_id") else None
        return Response(_snapshot(enrollment, session))


class ScanAttendanceSerializer(ScanSerializer):
    session_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=AttendanceRecord.Status.choices,
                                     default=AttendanceRecord.Status.PRESENT)


class ScanAttendanceView(APIView):
    """Action 1 — mark present (the default) without retyping anything."""

    permission_classes = IS_ENV_OWNER
    throttle_classes = [ScanRateThrottle]

    def post(self, request):
        ser = ScanAttendanceSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        enrollment = _enrollment_for(request, ser.validated_data["token"])
        session = _session_for(request, ser.validated_data["session_id"])
        _record_any("attendance", session, enrollment, ser.validated_data["status"])
        return Response(_snapshot(enrollment, session))


class ScanRecitationSerializer(ScanSerializer):
    session_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=RecitationRecord.Status.choices)


class ScanRecitationView(APIView):
    """Action 2 — exactly two outcomes: studied / not studied."""

    permission_classes = IS_ENV_OWNER
    throttle_classes = [ScanRateThrottle]

    def post(self, request):
        ser = ScanRecitationSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        enrollment = _enrollment_for(request, ser.validated_data["token"])
        session = _session_for(request, ser.validated_data["session_id"])
        _record_any("recitation", session, enrollment, ser.validated_data["status"])
        return Response(_snapshot(enrollment, session))


class ScanPaymentView(APIView):
    """Action 3 — record this month's fee as paid.

    The amount comes from the Grade (INV-5: the Grade owns the fee), never
    from the client, so a scan cannot post an arbitrary amount. Re-scanning an
    already-paid month keeps the original `paid_at` instead of creating a
    second record.
    """

    permission_classes = IS_ENV_OWNER
    throttle_classes = [ScanRateThrottle]

    def post(self, request):
        ser = ScanSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        enrollment = _enrollment_for(request, ser.validated_data["token"])
        if not enrollment.is_active:
            raise serializers.ValidationError({"detail": "الطالب غير نشط."})
        month = current_month()
        for _ in range(2):
            try:
                with transaction.atomic():
                    rec, created = MonthlyPayment.objects.select_for_update().get_or_create(
                        enrollment=enrollment, month=month,
                        defaults={
                            "environment": request.environment,
                            "amount": enrollment.grade.fee_amount,
                            "status": MonthlyPayment.Status.PAID,
                            "paid_at": timezone.now(),
                            "note": "تم التسجيل عبر مسح رمز الطالب.",
                        },
                    )
                    if not created and rec.status != MonthlyPayment.Status.PAID:
                        rec.status = MonthlyPayment.Status.PAID
                        rec.paid_at = rec.paid_at or timezone.now()
                        rec.save(update_fields=["status", "paid_at", "updated_at"])
                break
            except IntegrityError:
                continue
        return Response(_snapshot(enrollment, None) | {"payment_status": MonthlyPayment.Status.PAID})


class RotateBadgeView(APIView):
    """Invalidate a lost or shared badge and issue a new handle."""

    permission_classes = IS_ENV_OWNER
    throttle_classes = [ScanRateThrottle]

    def post(self, request, enrollment_id):
        enrollment = generics.get_object_or_404(
            Enrollment.objects.filter(environment=request.environment), pk=enrollment_id
        )
        return Response({"enrollment_id": enrollment.id, "qr_token": enrollment.rotate_qr_token()},
                        status=status.HTTP_200_OK)
