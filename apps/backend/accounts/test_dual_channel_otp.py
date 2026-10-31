"""
Activation and signup with a CHOICE of OTP channel (SMS or email), plus the
student-code proof required before a student account can be activated.
"""
from unittest import mock

from django.core import mail
from rest_framework.test import APIClient

from academics.models import Enrollment
from accounts.delivery import OTPDeliveryError
from accounts.models import PendingAuth, User
from accounts.testing import TestCase, ensure_active_enrollment

PW = "Str0ng!Pass1"
CLAIM = "/api/v1/auth/student/claim/"
ACTIVATE = "/api/v1/auth/student/claim/activate/"
VERIFY = "/api/v1/auth/otp/student-claim/verify/"
PHONE = "201230007777"


def new_student(phone=PHONE, active_enrollment=True):
    s = User.objects.create_user(role=User.Role.STUDENT, name="طالب", phone=phone, is_active=False, password=None)
    e = ensure_active_enrollment(s, active=active_enrollment)
    return s, e


class StudentCodeActivationTests(TestCase):
    def setUp(self):
        self.c = APIClient()
        self.student, self.enrollment = new_student()
        self.code = self.enrollment.qr_token

    def request(self, **kw):
        body = {"channel": "phone", "phone": PHONE, "student_code": self.code, **kw}
        return self.c.post(CLAIM, body, format="json")

    def finish(self, r, password=PW):
        pid, otp = r.data["pending_id"], r.data["debug_otp"]
        v = self.c.post(VERIFY, {"pending_id": pid, "code": otp})
        self.assertEqual(v.status_code, 200, v.data)
        return self.c.post(ACTIVATE, {"pending_id": pid, "password": password, "password2": password})

    # --- phone channel ------------------------------------------------------
    def test_phone_channel_sends_an_sms_and_activates(self):
        r = self.request()
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["channel"], "phone")
        self.assertEqual(len(mail.outbox), 0, "SMS channel must not send email")
        a = self.finish(r)
        self.assertEqual(a.status_code, 201, a.data)
        self.assertNotIn("access", a.data)
        login = APIClient().post("/api/v1/auth/student/login/", {"phone": PHONE, "password": PW})
        self.assertEqual(login.status_code, 200)

    def test_phone_channel_requires_the_phone_on_the_students_record(self):
        other = self.request(phone="201230008888")
        unknown = self.request(student_code="AAAAAA")
        self.assertEqual(other.status_code, 400)
        self.assertEqual(other.json(), unknown.json(), "wrong phone and wrong code must be indistinguishable")
        self.assertEqual(PendingAuth.objects.count(), 0)

    # --- email channel ------------------------------------------------------
    def test_email_channel_mails_the_code_and_stores_the_verified_email(self):
        r = self.request(channel="email", email="Student.Gmail@Gmail.com")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(r.data["channel"], "email")
        self.assertNotIn("student.gmail", r.data["target_masked"].lower())  # shown masked, not in full
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["student.gmail@gmail.com"])
        self.assertIn(r.data["debug_otp"], mail.outbox[0].body)

        a = self.finish(r)
        self.assertEqual(a.status_code, 201, a.data)
        self.assertTrue(a.data["phone_hint"].endswith(PHONE[-4:]))
        self.assertNotIn(PHONE, str(a.data), "the full phone must not be disclosed")
        self.student.refresh_from_db()
        self.assertEqual(self.student.email, "student.gmail@gmail.com")
        self.assertTrue(self.student.is_active and self.student.is_verified)
        # Login is still by PHONE + password.
        self.assertEqual(APIClient().post("/api/v1/auth/student/login/", {"phone": PHONE, "password": PW}).status_code, 200)

    def test_email_used_by_another_account_is_refused_before_anything_is_sent(self):
        User.objects.create_user(role=User.Role.TEACHER, name="T", email="taken@gmail.com", phone="201230009991",
                                 password=PW, is_active=True)
        r = self.request(channel="email", email="taken@gmail.com")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "email_in_use")
        self.assertEqual(len(mail.outbox), 0)

    def test_email_taken_between_request_and_activation_is_a_conflict(self):
        r = self.request(channel="email", email="late@gmail.com")
        User.objects.create_user(role=User.Role.TEACHER, name="T", email="late@gmail.com", phone="201230009992",
                                 password=PW, is_active=True)
        a = self.finish(r)
        self.assertEqual(a.status_code, 409)
        self.student.refresh_from_db()
        self.assertFalse(self.student.is_active)

    # --- the student code ----------------------------------------------------
    def test_the_code_is_mandatory(self):
        r = self.c.post(CLAIM, {"channel": "phone", "phone": PHONE}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIn("student_code", r.data["fields"])

    def test_a_code_with_no_matching_student_sends_nothing(self):
        r = self.request(channel="email", email="x@gmail.com", student_code="ZZZZZZ")
        self.assertEqual((r.status_code, r.data["code"]), (400, "not_found"))
        self.assertEqual(len(mail.outbox), 0)
        self.assertEqual(PendingAuth.objects.count(), 0)

    def test_code_is_forgiving_about_case_spaces_and_dashes(self):
        typed = f"{self.code[:3].lower()}-{self.code[3:].lower()} "
        self.assertEqual(self.request(student_code=typed).status_code, 200)

    def test_a_deactivated_enrolment_code_looks_like_any_unknown_code(self):
        Enrollment.objects.filter(pk=self.enrollment.pk).update(is_active=False)
        r, unknown = self.request(), self.request(student_code="AAAAAA")
        self.assertEqual(r.json(), unknown.json())

    def test_an_already_active_account_cannot_be_claimed_with_its_code(self):
        User.objects.filter(pk=self.student.pk).update(is_active=True)
        r = self.request()
        self.assertEqual((r.status_code, r.data["code"]), (400, "not_found"))

    def test_the_code_of_one_student_cannot_activate_another_students_phone(self):
        other, other_enr = new_student(phone="201230006666")
        r = self.request(phone="201230006666", student_code=self.code)
        self.assertEqual((r.status_code, r.data["code"]), (400, "not_found"))
        other.refresh_from_db()
        self.assertFalse(other.is_active)

    def test_a_new_request_invalidates_the_previous_code_across_channels(self):
        first = self.request()
        second = self.request(channel="email", email="n@gmail.com")
        bad = self.c.post(VERIFY, {"pending_id": first.data["pending_id"], "code": first.data["debug_otp"]})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.c.post(VERIFY, {"pending_id": second.data["pending_id"], "code": second.data["debug_otp"]}).status_code, 200)

    def test_resend_uses_the_chosen_channel(self):
        r = self.request(channel="email", email="again@gmail.com")
        self.assertEqual(len(mail.outbox), 1)
        rr = self.c.post("/api/v1/auth/otp/student-claim/resend/", {"pending_id": r.data["pending_id"]})
        self.assertEqual(rr.status_code, 200)
        self.assertEqual(len(mail.outbox), 2)
        self.assertEqual(mail.outbox[1].to, ["again@gmail.com"])
        self.assertIn(rr.data["debug_otp"], mail.outbox[1].body)

    def test_email_requests_are_throttled_per_address(self):
        codes = [self.request(channel="email", email="spam@gmail.com", student_code="AAAAAA").status_code for _ in range(6)]
        self.assertEqual(codes[-1], 429)

    def test_delivery_failure_is_reported_and_leaves_no_usable_flow(self):
        with mock.patch("accounts.views.deliver", side_effect=OTPDeliveryError("smtp down")):
            r = self.request(channel="email", email="down@gmail.com")
        self.assertEqual((r.status_code, r.data["code"]), (503, "otp_delivery_failed"))
        self.assertEqual(PendingAuth.objects.count(), 0)


class TeacherSignupChannelTests(TestCase):
    def setUp(self):
        self.c = APIClient()

    def body(self, **kw):
        return {"name": "معلم", "email": "teach@gmail.com", "phone": "201230001234",
                "password": PW, "password2": PW, **kw}

    def test_default_is_sms_to_the_phone(self):
        r = self.c.post("/api/v1/auth/teacher/signup/", self.body())
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["channel"], r.data["target"]), ("phone", "201230001234"))
        self.assertEqual(len(mail.outbox), 0)

    def test_teacher_can_choose_email(self):
        r = self.c.post("/api/v1/auth/teacher/signup/", self.body(otp_channel="email"))
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual((r.data["channel"], r.data["target"]), ("email", "teach@gmail.com"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["teach@gmail.com"])
        self.assertIn(r.data["debug_otp"], mail.outbox[0].body)

    def test_email_signup_completes_end_to_end(self):
        r = self.c.post("/api/v1/auth/teacher/signup/", self.body(otp_channel="email"))
        pid = r.data["pending_id"]
        self.assertEqual(self.c.post("/api/v1/auth/otp/teacher-signup/verify/", {"pending_id": pid, "code": r.data["debug_otp"]}).status_code, 200)
        env = self.c.post("/api/v1/auth/teacher/signup/environment/", {"pending_id": pid, "name": "بيئتي"})
        self.assertEqual(env.status_code, 201, env.data)
        self.assertTrue(User.objects.get(email="teach@gmail.com").is_verified)

    def test_unknown_channel_is_rejected(self):
        r = self.c.post("/api/v1/auth/teacher/signup/", self.body(otp_channel="pigeon"))
        self.assertEqual(r.status_code, 400)

    def test_switching_channel_invalidates_the_first_code(self):
        a = self.c.post("/api/v1/auth/teacher/signup/", self.body())
        b = self.c.post("/api/v1/auth/teacher/signup/", self.body(otp_channel="email"))
        self.assertEqual(self.c.post("/api/v1/auth/otp/teacher-signup/verify/", {"pending_id": a.data["pending_id"], "code": a.data["debug_otp"]}).status_code, 400)
        self.assertEqual(self.c.post("/api/v1/auth/otp/teacher-signup/verify/", {"pending_id": b.data["pending_id"], "code": b.data["debug_otp"]}).status_code, 200)

    def test_email_failure_is_reported_to_the_teacher(self):
        with mock.patch("accounts.views.deliver", side_effect=OTPDeliveryError("down")):
            r = self.c.post("/api/v1/auth/teacher/signup/", self.body(otp_channel="email"))
        self.assertEqual(r.status_code, 503)


class ResetDeliveryTests(TestCase):
    """Reset flows now really deliver — but never for an unknown account."""

    def test_known_teacher_by_email_gets_mail_unknown_gets_none_and_same_response_shape(self):
        User.objects.create_user(role=User.Role.TEACHER, name="T", email="known@gmail.com", phone="201230005432",
                                 password=PW, is_active=True)
        c = APIClient()
        known = c.post("/api/v1/auth/teacher/forgot/", {"identifier": "known@gmail.com"})
        self.assertEqual(len(mail.outbox), 1)
        unknown = c.post("/api/v1/auth/teacher/forgot/", {"identifier": "ghost@gmail.com"})
        self.assertEqual(len(mail.outbox), 1, "no mail for an account that does not exist")
        self.assertEqual((known.status_code, set(known.data)), (unknown.status_code, set(unknown.data)))


class CheckOTPDeliveryCommandTests(TestCase):
    def test_email_goes_through_the_configured_backend(self):
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("check_otp_delivery", email="teacher@gmail.com", stdout=out)
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["teacher@gmail.com"])
        self.assertIn("accepted", out.getvalue())

    def test_a_delivery_failure_is_reported_as_an_error(self):
        from django.core.management import CommandError, call_command

        with mock.patch("accounts.delivery.EmailMultiAlternatives.send", side_effect=OSError("smtp down")):
            with self.assertRaises(CommandError):
                call_command("check_otp_delivery", email="teacher@gmail.com")

    def test_email_has_branded_html_alternative_with_the_code(self):
        from django.core import mail

        from accounts.delivery import send_otp

        send_otp("email", "x@gmail.com", "048213")
        m = mail.outbox[-1]
        self.assertIn("048213", m.body)
        html, mime = m.alternatives[0]
        self.assertEqual(mime, "text/html")
        self.assertIn('dir="rtl"', html)
        self.assertEqual(sum(f">{d}</div>" in html for d in "048213"), 6)

    def test_needs_a_target(self):
        from django.core.management import CommandError, call_command

        with self.assertRaises(CommandError):
            call_command("check_otp_delivery")
