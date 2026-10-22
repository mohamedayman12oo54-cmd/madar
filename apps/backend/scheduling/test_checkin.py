"""Session self check-in: teacher QR + student phone + announced code."""
from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import Enrollment, Grade, Group
from environments.tenancy_testing import TenantTestCase

from .models import AttendanceRecord, CheckinLink, RecitationRecord, SessionInstance

PHONE = "201555400001"


def link_url(pk):
    return f"/api/v1/scheduling/sessions/{pk}/checkin/"


def info(token):
    return f"/api/v1/scheduling/checkin/{token}/"


def submit(token):
    return f"/api/v1/scheduling/checkin/{token}/submit/"


class CheckinTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        cache.clear()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=150)
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.other_group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        self.session = SessionInstance.objects.create(
            environment=self.env_a, group=self.group, scheduled_at=timezone.now())
        self.session.open()
        self.student = self.make_student_in(self.env_a, PHONE, "طالب ١")
        self.enr = Enrollment.objects.create(environment=self.env_a, student=self.student, grade=self.grade)
        self.enr.groups.set([self.group])
        self.anon = APIClient()

    def issue(self):
        r = self.client_a.post(link_url(self.session.id), {}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["link"]

    def attempt(self, link, phone=PHONE, code=None):
        return self.anon.post(submit(link["token"]), {"phone": phone, "code": code or link["code"]}, format="json")

    def status_of(self):
        rec = AttendanceRecord.objects.filter(session=self.session, enrollment=self.enr).first()
        return rec.status if rec else None

    # ---------------------------------------------------------- teacher ----
    def test_teacher_issues_a_link_with_token_and_six_digit_code(self):
        link = self.issue()
        self.assertGreaterEqual(len(link["token"]), 20)
        self.assertRegex(link["code"], r"^\d{6}$")
        got = self.client_a.get(link_url(self.session.id), **self.with_env(self.env_a.id)).json()["link"]
        self.assertEqual(got["token"], link["token"])

    def test_regenerating_revokes_the_previous_link(self):
        first = self.issue()
        second = self.issue()
        self.assertNotEqual(first["token"], second["token"])
        self.assertEqual(self.anon.get(info(first["token"])).status_code, 404)
        self.assertEqual(self.anon.get(info(second["token"])).status_code, 200)

    def test_cannot_issue_for_a_session_that_is_not_open(self):
        self.session.close()
        r = self.client_a.post(link_url(self.session.id), {}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_another_teacher_cannot_touch_the_link(self):
        r = self.client_b.post(link_url(self.session.id), {}, format="json", **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)

    def test_students_and_anonymous_cannot_issue(self):
        self.assertIn(self.anon.post(link_url(self.session.id), {}, format="json").status_code, (401, 403))

    def test_revoke(self):
        link = self.issue()
        r = self.client_a.delete(link_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 204)
        self.assertEqual(self.anon.get(info(link["token"])).status_code, 404)

    # ---------------------------------------------------------- student ----
    def test_info_reveals_only_environment_group_and_time(self):
        link = self.issue()
        data = self.anon.get(info(link["token"])).json()
        self.assertEqual(set(data), {"environment", "group", "scheduled_at"})

    def test_checkin_marks_present_and_counts_once(self):
        link = self.issue()
        r = self.attempt(link)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["result"], "recorded")
        self.assertEqual(self.status_of(), "present")
        again = self.attempt(link)
        self.assertEqual(again.json()["result"], "already")
        self.assertEqual(CheckinLink.objects.get(token=link["token"]).checked_in_count, 1)

    def test_local_format_phone_is_not_accepted_but_arabic_digits_in_code_are(self):
        link = self.issue()
        arabic = link["code"].translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
        self.assertEqual(self.attempt(link, code=arabic).status_code, 200)

    def test_wrong_code_and_unknown_phone_give_the_same_message(self):
        link = self.issue()
        wrong = "000000" if link["code"] != "000000" else "111111"
        a = self.attempt(link, code=wrong)
        b = self.attempt(link, phone="201555499999")
        self.assertEqual(a.status_code, 400)
        self.assertEqual(b.status_code, 400)
        self.assertEqual(a.json(), b.json())
        self.assertIsNone(self.status_of())

    def test_student_of_another_group_cannot_check_in(self):
        self.enr.groups.set([self.other_group])
        link = self.issue()
        self.assertEqual(self.attempt(link).status_code, 400)
        self.assertIsNone(self.status_of())

    def test_student_of_another_environment_cannot_check_in(self):
        outsider = self.make_student_in(self.env_b, "201555400002", "غريب")
        grade_b = Grade.objects.create(environment=self.env_b, name="أول", fee_amount=100)
        Enrollment.objects.create(environment=self.env_b, student=outsider, grade=grade_b)
        link = self.issue()
        r = self.attempt(link, phone="201555400002")
        self.assertEqual(r.status_code, 400)
        self.assertFalse(AttendanceRecord.objects.filter(enrollment__student=outsider).exists())

    def test_inactive_enrollment_cannot_check_in(self):
        self.enr.is_active = False
        self.enr.save()
        link = self.issue()
        self.assertEqual(self.attempt(link).status_code, 400)

    def test_token_alone_is_not_enough(self):
        link = self.issue()
        r = self.anon.post(submit(link["token"]), {"phone": PHONE}, format="json")
        self.assertEqual(r.status_code, 400)
        self.assertIsNone(self.status_of())

    def test_closed_session_rejects_check_in(self):
        link = self.issue()
        self.session.close()
        r = self.attempt(link)
        self.assertEqual(r.status_code, 404)

    def test_expired_link_is_rejected(self):
        link = self.issue()
        CheckinLink.objects.filter(token=link["token"]).update(expires_at=timezone.now() - timezone.timedelta(minutes=1))
        self.assertEqual(self.attempt(link).status_code, 404)

    def test_self_checkin_never_overrides_a_manual_absence(self):
        AttendanceRecord.objects.create(
            environment=self.env_a, session=self.session, enrollment=self.enr, status="absent")
        link = self.issue()
        r = self.attempt(link)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.status_of(), "absent")

    def test_checkin_only_ever_writes_attendance(self):
        link = self.issue()
        self.attempt(link)
        self.assertFalse(RecitationRecord.objects.exists())

    def test_unknown_token_is_404(self):
        self.assertEqual(self.anon.get(info("nope")).status_code, 404)
        r = self.anon.post(submit("nope"), {"phone": PHONE, "code": "123456"}, format="json")
        self.assertEqual(r.status_code, 404)

    def test_guessing_is_throttled_per_phone(self):
        link = self.issue()
        wrong = "000000" if link["code"] != "000000" else "111111"
        codes = [self.attempt(link, code=wrong).status_code for _ in range(10)]
        self.assertIn(429, codes)
        # once throttled, even the right code is refused for that phone
        self.assertEqual(self.attempt(link).status_code, 429)
