"""
Guardian (ولي الأمر) read-only portal.

Flow: phone -> OTP -> short-lived session bound to one Enrollment.

Strictly read-only, and scoped to the single enrollment whose `parent_phone`
the caller proved they control. Private teacher notes are NEVER included —
they are teacher-only, and a guardian is not the teacher.
"""
from django.db import transaction
from rest_framework import serializers, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment
from accounts.models import PendingAuth, supersede_pending
from accounts.serializers import clean_phone, normalize_student_code
from accounts.throttles import (
    GuardianCodeRateThrottle, GuardianLoginRateThrottle, GuardianPhoneRateThrottle,
    OTPRequestRateThrottle, OTPTargetRateThrottle, SensitiveRateThrottle,
)
from accounts.views import consume_pending, otp_debug_field, send_pending_code
from config.months import current_month
from evaluation.models import MonthlyRating, StudentState
from financials.models import MonthlyPayment
from notifications.models import Notification
from scheduling.models import AttendanceRecord, RecitationRecord

from .auth import IsParent, SESSION_TTL_SECONDS, guardian_visible_q, issue_session

# One message for every failure mode, so the endpoint never reveals whether a
# number belongs to a guardian, a teacher, or nobody.
CODE_LOGIN_FAILED = "تعذّر الدخول. تأكد من رقم هاتفك المسجّل لدى المدرّس ومن كود الطالب، وأن ابنك فعّل حسابه."
NOT_FOUND = "لا يوجد طالب مفعّل مرتبط بهذا الرقم. تأكد من الرقم، أو من تفعيل الطالب لحسابه."


def guardian_enrollments(phone):
    """Every child this number may follow: recorded by a teacher as the
    guardian phone, enrolment active, AND the child's own account activated.
    One guardian can have several children (even with different teachers)."""
    return (Enrollment.objects.filter(parent_phone=phone, is_active=True)
            .filter(guardian_visible_q())
            .select_related("grade", "student", "environment").order_by("-id"))


class RequestSerializer(serializers.Serializer):
    phone = serializers.CharField()

    def validate_phone(self, value):
        return clean_phone(value)


class GuardianRequestView(APIView):
    """Step 1 — prove you control the number the teacher recorded."""

    permission_classes = [AllowAny]
    throttle_classes = [OTPRequestRateThrottle, OTPTargetRateThrottle]

    def post(self, request):
        ser = RequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        phone = ser.validated_data["phone"]

        enrollments = list(guardian_enrollments(phone))
        if not enrollments:
            raise serializers.ValidationError({"detail": NOT_FOUND, "code": "not_found"})

        # Only one live guardian code per number.
        supersede_pending(PendingAuth.Purpose.PARENT_ACCESS, phone)
        pending = PendingAuth(
            purpose=PendingAuth.Purpose.PARENT_ACCESS,
            payload={"enrollment_ids": [e.id for e in enrollments]},
            target=phone,
        )
        code = pending.set_new_otp()
        pending.save()
        send_pending_code(pending, code, strict=False)
        return Response(
            {"pending_id": pending.id, "target": pending.target,
             "message": "تم إرسال رمز التحقق إلى رقمك.", **otp_debug_field(code)},
            status=status.HTTP_200_OK,
        )


def session_response(enrollments):
    children = [{
        "token": issue_session(e),
        "student_name": e.display_name,
        "grade": e.grade.name,
        "teacher_environment": e.environment.name,
    } for e in enrollments]
    return {
        # `token` & friends = the first child, kept so a single-child
        # guardian (the common case) needs no extra step.
        **children[0],
        "expires_in": SESSION_TTL_SECONDS,
        "children": children,
    }


class CodeLoginSerializer(serializers.Serializer):
    phone = serializers.CharField()
    student_code = serializers.CharField(max_length=32)

    def validate_phone(self, value):
        return clean_phone(value)

    def validate_student_code(self, value):
        code = normalize_student_code(value)
        if not code:
            raise serializers.ValidationError("أدخل كود الطالب.")
        return code


class GuardianCodeLoginView(APIView):
    """Sign in with the guardian phone the teacher recorded AND the student
    code of that child — no OTP.

    Two things the guardian must know, and both must belong to the SAME
    enrolment. The session is bound to that one child. Every failure (unknown
    code, wrong phone, child not activated, deactivated) is the same message,
    so the endpoint is no oracle for codes, numbers or children. Guessing is
    capped per IP, per phone and per code (accounts/throttles.py)."""

    permission_classes = [AllowAny]
    throttle_classes = [GuardianLoginRateThrottle, GuardianPhoneRateThrottle, GuardianCodeRateThrottle]

    def post(self, request):
        ser = CodeLoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        enrollment = guardian_enrollments(ser.validated_data["phone"]).filter(
            qr_token=ser.validated_data["student_code"]).first()
        if enrollment is None:
            raise serializers.ValidationError({"detail": CODE_LOGIN_FAILED, "code": "not_found"})
        return Response(session_response([enrollment]))


class VerifySerializer(serializers.Serializer):
    pending_id = serializers.UUIDField()


class GuardianVerifyView(APIView):
    """Step 2 — exchange a verified OTP flow for a read-only session."""

    permission_classes = [AllowAny]
    throttle_classes = [SensitiveRateThrottle]

    def post(self, request):
        ser = VerifySerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        pending = PendingAuth.objects.filter(
            pk=ser.validated_data["pending_id"],
            purpose=PendingAuth.Purpose.PARENT_ACCESS,
        ).first()
        if pending is None or not pending.verified:
            raise serializers.ValidationError({"detail": "تحقّق من الرمز أولًا.", "code": "not_verified"})

        with transaction.atomic():
            if not consume_pending(pending):
                raise serializers.ValidationError({"detail": "انتهت صلاحية الطلب.", "code": "expired"})
            # Re-evaluated now (not trusted from the request step): a child may
            # have been deactivated, or the number corrected, in between.
            enrollments = list(guardian_enrollments(pending.target).filter(
                pk__in=pending.payload.get("enrollment_ids") or []))
        if not enrollments:
            raise serializers.ValidationError({"detail": NOT_FOUND, "code": "not_found"})

        return Response(session_response(enrollments))


class GuardianOverviewView(APIView):
    """Everything a guardian may see, in one read.

    Attendance, recitation, payments, monthly evaluation — and the same
    notifications the student received, so a guardian is not told less than
    their child. Private teacher notes are excluded by construction: this view
    never touches that table.
    """

    permission_classes = [IsParent]

    def get(self, request):
        enrollment = request.user.enrollment

        attendance = AttendanceRecord.objects.filter(enrollment=enrollment)
        present = attendance.filter(status=AttendanceRecord.Status.PRESENT).count()
        absent = attendance.filter(status=AttendanceRecord.Status.ABSENT).count()

        recitation = RecitationRecord.objects.filter(enrollment=enrollment)
        studied = recitation.filter(status=RecitationRecord.Status.STUDIED).count()
        not_studied = recitation.filter(status=RecitationRecord.Status.NOT_STUDIED).count()

        payments = MonthlyPayment.objects.filter(enrollment=enrollment).order_by("-month")[:12]
        this_month = next((p for p in payments if p.month == current_month()), None)

        states = StudentState.objects.filter(enrollment=enrollment).order_by("-month")[:12]
        # Only PUBLISHED ratings: a draft is the teacher's working note.
        ratings = (MonthlyRating.objects.filter(enrollment=enrollment, published_at__isnull=False)
                   .order_by("-month")[:12])

        notes_by_month = {r.month: r for r in ratings}
        evaluation = [{
            "month": s.month.strftime("%Y-%m"),
            "state": s.state,
            "state_label": s.get_state_display(),
            "rating": notes_by_month[s.month].value if s.month in notes_by_month else None,
        } for s in states]

        notifications = Notification.objects.filter(
            environment=enrollment.environment, recipient=enrollment.student,
        ).order_by("-created_at")[:30]

        return Response({
            "student": {
                "name": enrollment.display_name,
                "grade": enrollment.grade.name,
                "teacher_environment": enrollment.environment.name,
            },
            "attendance": {
                "present": present, "absent": absent, "total": present + absent,
                "recent": [{"date": a.session.scheduled_at, "status": a.status}
                           for a in attendance.select_related("session").order_by("-session__scheduled_at")[:15]],
            },
            "recitation": {
                "studied": studied, "not_studied": not_studied, "total": studied + not_studied,
                "recent": [{"date": r.session.scheduled_at, "status": r.status}
                           for r in recitation.select_related("session").order_by("-session__scheduled_at")[:15]],
            },
            "payments": {
                "this_month": {
                    "month": current_month().strftime("%Y-%m"),
                    "status": this_month.status if this_month else MonthlyPayment.Status.UNPAID,
                    "amount": str(this_month.amount) if this_month else str(enrollment.grade.fee_amount),
                },
                "history": [{"month": p.month.strftime("%Y-%m"), "status": p.status,
                             "amount": str(p.amount), "paid_at": p.paid_at} for p in payments],
            },
            "evaluation": evaluation,
            "notifications": [{
                "id": n.id, "type": n.type, "type_label": n.get_type_display(),
                "title": n.title, "body": n.body, "created_at": n.created_at,
            } for n in notifications],
        })
