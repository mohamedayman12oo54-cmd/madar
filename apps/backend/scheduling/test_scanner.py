"""Teacher QR scanner: badge security + the three documented actions."""
from django.utils import timezone

from academics.models import Enrollment, Grade, Group
from environments.tenancy_testing import TenantTestCase
from financials.models import MonthlyPayment

from .models import AttendanceRecord, RecitationRecord, SessionInstance

RESOLVE = "/api/v1/scheduling/scan/resolve/"
ATTEND = "/api/v1/scheduling/scan/attendance/"
RECITE = "/api/v1/scheduling/scan/recitation/"
PAY = "/api/v1/scheduling/scan/payment/"


def rotate_url(pk):
    return f"/api/v1/scheduling/scan/badge/{pk}/rotate/"


class ScannerTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=150)
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.session = SessionInstance.objects.create(
            environment=self.env_a, group=self.group, scheduled_at=timezone.now())
        self.session.open()
        self.student = self.make_student_in(self.env_a, "201555300001", "طالب ١")
        self.enr = Enrollment.objects.create(environment=self.env_a, student=self.student, grade=self.grade)
        self.enr.groups.set([self.group])

    def post(self, url, body, client=None, env=None):
        return (client or self.client_a).post(
            url, body, format="json", **self.with_env((env or self.env_a).id))

    # ---------------------------------------------------------- badge ----
    def test_badge_code_is_six_readable_characters(self):
        from academics.models import BADGE_ALPHABET

        code = self.enr.qr_token
        self.assertEqual(len(code), 6)
        self.assertTrue(set(code) <= set(BADGE_ALPHABET), code)
        # Look-alike characters are excluded so a code can be read aloud or
        # typed in without 0/O or 1/I/L confusion.
        self.assertFalse(set("01OIL") & set(BADGE_ALPHABET))

    def test_codes_are_unique_and_not_derived_from_the_row_id(self):
        codes = [self.enr.qr_token]
        for i in range(5):
            e = Enrollment.objects.create(
                environment=self.env_a,
                student=self.make_student_in(self.env_a, f"20155530001{i}", f"ب{i}"),
                grade=self.grade)
            codes.append(e.qr_token)
        self.assertEqual(len(set(codes)), len(codes), "codes must be unique")
        for code in codes:
            self.assertNotIn(str(self.enr.id), code[:2])

    def test_rotation_yields_a_different_code_each_time(self):
        seen = {self.enr.qr_token}
        for _ in range(5):
            seen.add(self.enr.rotate_qr_token())
        self.assertEqual(len(seen), 6, "every rotation must issue a fresh code")

    def test_a_colliding_code_is_retried_rather_than_failing(self):
        """A 6-character space can collide; enrolment must not break."""
        from unittest import mock

        from academics import models as academics_models

        taken = self.enr.qr_token
        # Start from a code that is already in use, and make the retry deal a
        # free one. (The field default is bound at class definition, so the
        # collision has to be supplied explicitly.)
        with mock.patch.object(academics_models, "new_qr_token", lambda: "ZZZZZZ"):
            created = Enrollment.objects.create(
                environment=self.env_a,
                student=self.make_student_in(self.env_a, "201555300077", "ج"),
                grade=self.grade,
                qr_token=taken)
        self.assertEqual(created.qr_token, "ZZZZZZ")
        self.enr.refresh_from_db()
        self.assertEqual(self.enr.qr_token, taken, "the existing badge is untouched")

    def test_scan_resolves_the_student_without_recording_anything(self):
        r = self.post(RESOLVE, {"token": self.enr.qr_token, "session_id": self.session.id})
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["enrollment_id"], self.enr.id)
        self.assertIsNone(body["attendance"])
        self.assertIsNone(body["recitation"])
        self.assertEqual(body["payment_status"], "unpaid")
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_unknown_badge_is_rejected(self):
        self.assertEqual(self.post(RESOLVE, {"token": "x" * 43}).status_code, 404)

    def test_a_badge_from_another_environment_does_not_resolve(self):
        """Identical response to an unknown token: the scanner must not reveal
        that the badge exists under a different teacher."""
        foreign = Enrollment.objects.create(
            environment=self.env_b,
            student=self.make_student_in(self.env_b, "201555300002", "طالب ب"),
            grade=Grade.objects.create(environment=self.env_b, name="أول"))
        r = self.post(RESOLVE, {"token": foreign.qr_token})
        self.assertEqual(r.status_code, 404)
        self.assertEqual(r.status_code, self.post(RESOLVE, {"token": "y" * 43}).status_code)

    def test_rotating_a_badge_invalidates_the_previous_one(self):
        old = self.enr.qr_token
        r = self.post(rotate_url(self.enr.id), {})
        self.assertEqual(r.status_code, 200, r.content)
        new = r.json()["qr_token"]
        self.assertNotEqual(old, new)
        self.assertEqual(self.post(RESOLVE, {"token": old}).status_code, 404)
        self.assertEqual(self.post(RESOLVE, {"token": new}).status_code, 200)

    def test_students_cannot_use_the_scanner(self):
        self.assertEqual(
            self.client_b.post(RESOLVE, {"token": self.enr.qr_token}, format="json",
                               **self.with_env(self.env_a.id)).status_code, 403)

    # ------------------------------------------------------ attendance ---
    def test_scan_marks_present_without_retyping_anything(self):
        r = self.post(ATTEND, {"token": self.enr.qr_token, "session_id": self.session.id})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["attendance"], "present")
        rec = AttendanceRecord.objects.get(session=self.session, enrollment=self.enr)
        self.assertEqual((rec.status, rec.environment_id), ("present", self.env_a.id))

    def test_rescanning_does_not_create_a_duplicate(self):
        for _ in range(3):
            self.post(ATTEND, {"token": self.enr.qr_token, "session_id": self.session.id})
        self.assertEqual(AttendanceRecord.objects.filter(session=self.session, enrollment=self.enr).count(), 1)

    def test_an_intentional_correction_still_overwrites(self):
        self.post(ATTEND, {"token": self.enr.qr_token, "session_id": self.session.id})
        self.post(ATTEND, {"token": self.enr.qr_token, "session_id": self.session.id, "status": "absent"})
        self.assertEqual(AttendanceRecord.objects.get(session=self.session, enrollment=self.enr).status, "absent")

    def test_cannot_mark_into_another_environments_session(self):
        foreign_session = SessionInstance.objects.create(
            environment=self.env_b,
            group=Group.objects.create(
                environment=self.env_b, grade=Grade.objects.create(environment=self.env_b, name="ب"), name="G"),
            scheduled_at=timezone.now())
        r = self.post(ATTEND, {"token": self.enr.qr_token, "session_id": foreign_session.id})
        self.assertEqual(r.status_code, 404)
        self.assertFalse(AttendanceRecord.objects.exists())

    def test_scanner_cannot_bypass_the_open_session_rule(self):
        closed = SessionInstance.objects.create(
            environment=self.env_a, group=self.group, scheduled_at=timezone.now())  # never opened
        self.assertEqual(
            self.post(ATTEND, {"token": self.enr.qr_token, "session_id": closed.id}).status_code, 400)

    # ------------------------------------------------------- recitation --
    def test_recitation_records_exactly_the_two_allowed_outcomes(self):
        for value in ("studied", "not_studied"):
            r = self.post(RECITE, {"token": self.enr.qr_token, "session_id": self.session.id, "status": value})
            self.assertEqual(r.status_code, 200, r.content)
            self.assertEqual(r.json()["recitation"], value)
        self.assertEqual(RecitationRecord.objects.filter(session=self.session, enrollment=self.enr).count(), 1)

    def test_recitation_rejects_any_other_value(self):
        self.assertEqual(
            self.post(RECITE, {"token": self.enr.qr_token, "session_id": self.session.id,
                               "status": "maybe"}).status_code, 400)

    # ---------------------------------------------------------- fees -----
    def test_scan_records_this_months_fee_as_paid_at_the_grade_amount(self):
        r = self.post(PAY, {"token": self.enr.qr_token})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["payment_status"], "paid")
        rec = MonthlyPayment.objects.get(enrollment=self.enr)
        self.assertEqual((rec.status, str(rec.amount)), ("paid", "150.00"))
        self.assertIsNotNone(rec.paid_at)

    def test_the_client_cannot_dictate_the_amount(self):
        """INV-5: the Grade owns the fee, so a crafted payload must not set it."""
        self.post(PAY, {"token": self.enr.qr_token, "amount": "1.00", "status": "unpaid"})
        self.assertEqual(str(MonthlyPayment.objects.get(enrollment=self.enr).amount), "150.00")

    def test_rescanning_fees_does_not_duplicate_or_move_the_paid_time(self):
        first = self.post(PAY, {"token": self.enr.qr_token}).json()
        self.post(PAY, {"token": self.enr.qr_token})
        self.assertEqual(MonthlyPayment.objects.filter(enrollment=self.enr).count(), 1)
        self.assertEqual(self.post(PAY, {"token": self.enr.qr_token}).json()["month"], first["month"])


class ScannerAbuseTests(TenantTestCase):
    """Rate limiting on the scan endpoints: a scripted attacker grinding badge
    tokens gets cut off, while a normal classroom pace does not."""

    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=100)

    def test_badge_grinding_is_rate_limited(self):
        from unittest import mock

        from rest_framework.throttling import SimpleRateThrottle

        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"scan": "5/min"}):
            codes = [
                self.client_a.post(RESOLVE, {"token": f"guess-{i}"}, format="json",
                                   **self.with_env(self.env_a.id)).status_code
                for i in range(6)
            ]
        self.assertEqual(codes[:5], [404] * 5)   # wrong guesses, still answered
        self.assertEqual(codes[5], 429)          # then throttled

    def test_a_normal_classroom_pace_is_not_throttled(self):
        enr = Enrollment.objects.create(
            environment=self.env_a, student=self.make_student_in(self.env_a, "201555400001", "ط"), grade=self.grade)
        codes = {
            self.client_a.post(RESOLVE, {"token": enr.qr_token}, format="json",
                               **self.with_env(self.env_a.id)).status_code
            for _ in range(40)
        }
        self.assertEqual(codes, {200})


class BadgeCodeStrengthTests(TenantTestCase):
    """A 6-character code is short by design, so the controls around it carry
    the weight: tenant scoping, rotation, and rate limiting."""

    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.enr = Enrollment.objects.create(
            environment=self.env_a,
            student=self.make_student_in(self.env_a, "201555410001", "ط"),
            grade=self.grade)

    def test_the_code_space_is_large_enough_to_resist_guessing(self):
        from academics.models import BADGE_ALPHABET, BADGE_LENGTH

        combinations = len(BADGE_ALPHABET) ** BADGE_LENGTH
        self.assertGreater(combinations, 500_000_000, "code space too small")

    def test_a_valid_code_from_another_environment_still_fails(self):
        """Even a correctly guessed code is useless outside its own teacher's
        environment — the code alone is never sufficient."""
        r = self.client_b.post(RESOLVE, {"token": self.enr.qr_token},
                               format="json", **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)

    def test_a_hand_typed_code_is_normalised(self):
        """Lowercase, spaces and dashes are all accepted — a teacher reading a
        badge aloud should not fail on formatting."""
        code = self.enr.qr_token
        for typed in (code.lower(), f" {code} ", f"{code[:3]}-{code[3:]}", code.lower().replace("", "")):
            with self.subTest(typed=typed):
                r = self.client_a.post(RESOLVE, {"token": typed}, format="json",
                                       **self.with_env(self.env_a.id))
                self.assertEqual(r.status_code, 200, typed)
