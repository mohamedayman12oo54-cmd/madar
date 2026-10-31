"""Guardian read-only portal: who gets in, what they see, what they never see."""
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import Enrollment, Grade, Group
from accounts.models import PendingAuth
from environments.tenancy_testing import TenantTestCase
from evaluation.models import MonthlyRating, PrivateNote, StudentState
from financials.models import MonthlyPayment
from notifications.models import Notification
from scheduling.models import AttendanceRecord, RecitationRecord, SessionInstance

from .auth import issue_session

REQ = "/api/v1/parent/request/"
VERIFY = "/api/v1/parent/verify/"
OVERVIEW = "/api/v1/parent/overview/"
GUARDIAN = "201111222333"
SECRET_NOTE = "ملاحظة خاصة جدًا للمعلّم"


class _Base(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=200)
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.student = self.make_student_in(self.env_a, "201555800001", "ابن")
        self.activate(self.student)  # the child has claimed their account
        self.enr = Enrollment.objects.create(
            environment=self.env_a, student=self.student, grade=self.grade,
            student_name="ابن", parent_phone=GUARDIAN)
        self.enr.groups.set([self.group])
        self.anon = APIClient()

    @staticmethod
    def activate(student):
        student.is_active = True
        student.is_verified = True
        student.set_password("Str0ng-pass!")
        student.save()

    def session(self, when=None):
        s = SessionInstance.objects.create(
            environment=self.env_a, group=self.group, scheduled_at=when or timezone.now())
        s.open()
        return s

    def portal(self, enrollment=None):
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Parent " + issue_session(enrollment or self.enr))
        return c


    def _assert_no_session_possible(self):
        """The request answers 200 either way, but the flow it opens carries no enrolment."""
        r = self.anon.post(REQ, {"phone": GUARDIAN})
        self.assertEqual(r.status_code, 200)
        pending = PendingAuth.objects.get(pk=r.json()["pending_id"])
        self.assertEqual(pending.payload["enrollment_ids"], [])
        pending.verified = True
        pending.save(update_fields=["verified"])
        v = self.anon.post(VERIFY, {"pending_id": str(pending.pk)})
        self.assertEqual(v.status_code, 400)


class GuardianLoginTests(_Base):
    def test_a_recorded_guardian_number_receives_a_code_and_gets_a_session(self):
        r = self.anon.post(REQ, {"phone": GUARDIAN})
        self.assertEqual(r.status_code, 200, r.content)
        pending = PendingAuth.objects.get(pk=r.json()["pending_id"])
        pending.verified = True
        pending.save(update_fields=["verified"])
        v = self.anon.post(VERIFY, {"pending_id": str(pending.pk)})
        self.assertEqual(v.status_code, 200, v.content)
        self.assertIn("token", v.json())
        self.assertEqual(v.json()["student_name"], "ابن")

    def test_the_code_request_does_not_reveal_whether_a_number_is_a_guardian(self):
        known = self.anon.post(REQ, {"phone": GUARDIAN})
        unknown = self.anon.post(REQ, {"phone": "201111999888"})
        # A teacher's own number must look exactly the same — no oracle.
        teacher = self.anon.post(REQ, {"phone": self.teacher_a.phone})
        self.assertEqual({known.status_code, unknown.status_code, teacher.status_code}, {200})
        self.assertEqual(set(known.json()), set(unknown.json()))
        self.assertEqual(known.json()["message"], unknown.json()["message"])
        self.assertEqual(unknown.json()["message"], teacher.json()["message"])

    def test_an_unknown_number_gets_an_inert_flow_that_can_never_become_a_session(self):
        r = self.anon.post(REQ, {"phone": "201111999888"})
        pending = PendingAuth.objects.get(pk=r.json()["pending_id"])
        self.assertEqual(pending.payload["enrollment_ids"], [])
        # Even if the flow were somehow marked verified, there is nothing to exchange it for.
        pending.verified = True
        pending.save(update_fields=["verified"])
        v = self.anon.post(VERIFY, {"pending_id": str(pending.pk)})
        self.assertEqual(v.status_code, 400)
        self.assertNotIn("token", v.json())

    def test_an_unverified_flow_cannot_be_exchanged_for_a_session(self):
        pending_id = self.anon.post(REQ, {"phone": GUARDIAN}).json()["pending_id"]
        self.assertEqual(self.anon.post(VERIFY, {"pending_id": pending_id}).status_code, 400)

    def test_a_guardian_of_an_inactive_enrolment_loses_access(self):
        self.enr.is_active = False
        self.enr.save()
        self._assert_no_session_possible()
        self.assertEqual(self.portal().get(OVERVIEW).status_code, 401)

    def test_changing_the_recorded_number_revokes_an_existing_session(self):
        c = self.portal()
        self.assertEqual(c.get(OVERVIEW).status_code, 200)
        self.enr.parent_phone = "201111000999"
        self.enr.save()
        self.assertEqual(c.get(OVERVIEW).status_code, 401)

    def test_forged_and_tampered_tokens_are_refused(self):
        good = issue_session(self.enr)
        for bad in ["", "garbage", good[:-3] + "zzz", f"{self.enr.id}:{GUARDIAN}"]:
            c = APIClient()
            c.credentials(HTTP_AUTHORIZATION="Parent " + bad)
            self.assertEqual(c.get(OVERVIEW).status_code, 401, bad)

    def test_anonymous_cannot_read_the_portal(self):
        self.assertEqual(self.anon.get(OVERVIEW).status_code, 401)

    def test_an_open_portal_renews_its_own_token_and_never_expires_under_the_guardian(self):
        from datetime import timedelta
        from unittest import mock

        c = self.portal()
        r = c.post("/api/v1/parent/renew/")
        self.assertEqual(r.status_code, 200, r.content)
        fresh = r.json()["token"]
        self.assertEqual(r.json()["expires_in"], 60 * 60 * 24)
        later = APIClient()
        later.credentials(HTTP_AUTHORIZATION="Parent " + fresh)
        self.assertEqual(later.get(OVERVIEW).status_code, 200)
        # a token nobody renewed does expire (the tab was closed for more than a day)
        import time
        old = issue_session(self.enr)
        stale = APIClient()
        stale.credentials(HTTP_AUTHORIZATION="Parent " + old)
        with mock.patch.object(time, "time", return_value=time.time() + 60 * 60 * 25):
            self.assertEqual(stale.get(OVERVIEW).status_code, 401)
            self.assertEqual(stale.post("/api/v1/parent/renew/").status_code, 401)

    def test_renewal_follows_the_same_rules_as_every_request(self):
        c = self.portal()
        self.enr.parent_phone = "201111000999"
        self.enr.save()
        self.assertEqual(c.post("/api/v1/parent/renew/").status_code, 401)
        self.assertEqual(self.anon.post("/api/v1/parent/renew/").status_code, 401)


class GuardianNeedsNoAccountTests(_Base):
    """The guardian never activates anything. Their recorded phone is enough —
    but only once the CHILD has activated their own account."""

    def _full_login(self, phone=GUARDIAN):
        from django.contrib.auth.hashers import make_password

        r = self.anon.post(REQ, {"phone": phone})
        self.assertEqual(r.status_code, 200, r.content)
        pid = r.json()["pending_id"]
        PendingAuth.objects.filter(pk=pid).update(otp_hash=make_password("123456"))
        ok = self.anon.post(f"/api/v1/auth/otp/parent-access/verify/", {"pending_id": pid, "code": "123456"})
        self.assertEqual(ok.status_code, 200, ok.content)
        return self.anon.post(VERIFY, {"pending_id": pid})

    def test_guardian_logs_in_end_to_end_with_no_account_of_their_own(self):
        from accounts.models import User

        users_before = User.objects.count()
        v = self._full_login()
        self.assertEqual(v.status_code, 200, v.content)
        self.assertEqual(User.objects.count(), users_before)  # nothing created for the guardian
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Parent " + v.json()["token"])
        self.assertEqual(c.get(OVERVIEW).status_code, 200)

    def test_a_child_who_has_not_activated_gives_the_guardian_no_access(self):
        self.student.is_active = False
        self.student.save()
        # ...and the answer is indistinguishable from an unknown number (200), but nothing can be exchanged.
        r = self.anon.post(REQ, {"phone": GUARDIAN})
        unknown = self.anon.post(REQ, {"phone": "201111999888"})
        self.assertEqual(r.status_code, unknown.status_code)
        self.assertEqual(set(r.json()), set(unknown.json()))
        self.assertEqual(PendingAuth.objects.get(pk=r.json()["pending_id"]).payload["enrollment_ids"], [])

    def test_access_starts_the_moment_the_child_activates(self):
        self.student.is_active = False
        self.student.save()
        self._assert_no_session_possible()
        self.student.is_active = True
        self.student.save()
        r = self.anon.post(REQ, {"phone": GUARDIAN})
        self.assertEqual(r.status_code, 200)
        self.assertNotEqual(PendingAuth.objects.get(pk=r.json()["pending_id"]).payload["enrollment_ids"], [])

    def test_deactivating_the_child_ends_an_existing_guardian_session(self):
        c = self.portal()
        self.assertEqual(c.get(OVERVIEW).status_code, 200)
        self.student.is_active = False
        self.student.save()
        self.assertEqual(c.get(OVERVIEW).status_code, 401)

    def test_a_child_deactivated_between_code_and_exchange_is_refused(self):
        r = self.anon.post(REQ, {"phone": GUARDIAN})
        pid = r.json()["pending_id"]
        PendingAuth.objects.filter(pk=pid).update(verified=True)
        self.student.is_active = False
        self.student.save()
        self.assertEqual(self.anon.post(VERIFY, {"pending_id": pid}).status_code, 400)

    def test_one_number_following_two_children_gets_a_session_for_each(self):
        sibling = self.make_student_in(self.env_a, "201555800009", "أخت")
        self.activate(sibling)
        other = Enrollment.objects.create(environment=self.env_a, student=sibling, grade=self.grade,
                                          student_name="أخت", parent_phone=GUARDIAN)
        other.groups.set([self.group])
        body = self._full_login().json()
        self.assertEqual({c["student_name"] for c in body["children"]}, {"ابن", "أخت"})
        names = set()
        for child in body["children"]:
            c = APIClient()
            c.credentials(HTTP_AUTHORIZATION="Parent " + child["token"])
            names.add(c.get(OVERVIEW).json()["student"]["name"])
        self.assertEqual(names, {"ابن", "أخت"})

    def test_a_wrong_code_gives_no_session(self):
        r = self.anon.post(REQ, {"phone": GUARDIAN})
        pid = r.json()["pending_id"]
        bad = self.anon.post("/api/v1/auth/otp/parent-access/verify/", {"pending_id": pid, "code": "000000"})
        self.assertEqual(bad.status_code, 400)
        self.assertEqual(self.anon.post(VERIFY, {"pending_id": pid}).status_code, 400)

    def test_a_student_claim_code_cannot_be_used_on_the_guardian_endpoint(self):
        """Purpose pinning: another flow's pending_id is not a guardian code."""
        p = PendingAuth(purpose=PendingAuth.Purpose.STUDENT_CLAIM, target="x", payload={})
        p.set_new_otp()
        p.verified = True
        p.save()
        self.assertEqual(self.anon.post(VERIFY, {"pending_id": str(p.pk)}).status_code, 400)


class GuardianOverviewTests(_Base):
    def setUp(self):
        super().setUp()
        s1, s2 = self.session(), self.session()
        AttendanceRecord.objects.create(environment=self.env_a, session=s1, enrollment=self.enr, status="present")
        AttendanceRecord.objects.create(environment=self.env_a, session=s2, enrollment=self.enr, status="absent")
        RecitationRecord.objects.create(environment=self.env_a, session=s1, enrollment=self.enr, status="studied")
        month = timezone.now().date().replace(day=1)
        MonthlyPayment.objects.create(environment=self.env_a, enrollment=self.enr, month=month,
                                      amount=200, status="paid", paid_at=timezone.now())
        StudentState.objects.create(environment=self.env_a, enrollment=self.enr, month=month, state="good")
        MonthlyRating.objects.create(environment=self.env_a, enrollment=self.enr, month=month,
                                     value=4, published_at=timezone.now())
        PrivateNote.objects.create(environment=self.env_a, enrollment=self.enr, body=SECRET_NOTE)
        Notification.objects.create(environment=self.env_a, recipient=self.student,
                                    type="payment_due", title="رسوم", body="تذكير بالرسوم")
        self.body = self.portal().get(OVERVIEW)

    def test_guardian_sees_attendance_counts_and_recent_rows(self):
        d = self.body.json()["attendance"]
        self.assertEqual((d["present"], d["absent"], d["total"]), (1, 1, 2))
        self.assertEqual(len(d["recent"]), 2)

    def test_guardian_sees_recitation(self):
        d = self.body.json()["recitation"]
        self.assertEqual((d["studied"], d["not_studied"]), (1, 0))

    def test_guardian_sees_payment_status_for_this_month(self):
        d = self.body.json()["payments"]
        self.assertEqual(d["this_month"]["status"], "paid")
        self.assertEqual(d["this_month"]["amount"], "200.00")
        self.assertEqual(len(d["history"]), 1)

    def test_guardian_sees_the_monthly_evaluation_and_rating(self):
        row = self.body.json()["evaluation"][0]
        self.assertEqual(row["state"], "good")
        self.assertEqual(row["rating"], 4)

    def test_guardian_sees_the_same_notifications_as_the_student(self):
        titles = [n["title"] for n in self.body.json()["notifications"]]
        self.assertIn("رسوم", titles)

    def test_private_teacher_notes_are_never_exposed(self):
        self.assertNotIn(SECRET_NOTE, self.body.content.decode())

    def test_a_draft_rating_is_not_shown(self):
        MonthlyRating.objects.update(published_at=None)
        row = self.portal().get(OVERVIEW).json()["evaluation"][0]
        self.assertIsNone(row["rating"])


class GuardianIsolationTests(_Base):
    def setUp(self):
        super().setUp()
        other = self.make_student_in(self.env_a, "201555800002", "طفل آخر")
        self.other_enr = Enrollment.objects.create(
            environment=self.env_a, student=other, grade=self.grade,
            student_name="طفل آخر", parent_phone="201111555444")
        PrivateNote.objects.create(environment=self.env_a, enrollment=self.other_enr, body="سر آخر")

    def test_a_guardian_only_ever_sees_their_own_child(self):
        body = self.portal().get(OVERVIEW).content.decode()
        self.assertIn("ابن", body)
        self.assertNotIn("طفل آخر", body)
        self.assertNotIn("سر آخر", body)

    def test_the_portal_is_read_only(self):
        """No write verb is accepted anywhere in the guardian surface."""
        c = self.portal()
        for method in ("post", "put", "patch", "delete"):
            self.assertIn(getattr(c, method)(OVERVIEW).status_code, (401, 403, 405))

    def test_a_guardian_session_cannot_reach_teacher_or_student_apis(self):
        c = self.portal()
        for url in ["/api/v1/academics/enrollments/", "/api/v1/financials/monthly/",
                    "/api/v1/student/overview/", "/api/v1/evaluation/notes/",
                    "/api/v1/scheduling/sessions/", "/api/v1/knowledge/documents/"]:
            with self.subTest(url=url):
                self.assertIn(c.get(url, **self.with_env(self.env_a.id)).status_code, (401, 403),
                              f"{url} reachable with a guardian token")


class GuardianCodeLoginTests(_Base):
    """Phone + the child's student code, no OTP."""

    URL = "/api/v1/parent/login/"

    def login(self, phone=GUARDIAN, code=None, client=None):
        return (client or self.anon).post(
            self.URL, {"phone": phone, "student_code": code or self.enr.qr_token}, format="json")

    def test_phone_and_student_code_give_a_working_read_only_session(self):
        r = self.login()
        self.assertEqual(r.status_code, 200, r.content)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Parent " + r.json()["token"])
        self.assertEqual(c.get(OVERVIEW).status_code, 200)

    def test_code_is_forgiving_about_case_spaces_and_dashes(self):
        code = self.enr.qr_token
        sloppy = f" {code[:3].lower()}-{code[3:].lower()} "
        self.assertEqual(self.login(code=sloppy).status_code, 200)

    def test_every_failure_looks_the_same(self):
        other = self.make_student_in(self.env_a, "201555800002", "آخر")
        self.activate(other)
        other_enr = Enrollment.objects.create(
            environment=self.env_a, student=other, grade=self.grade,
            student_name="آخر", parent_phone="201099000111")
        wrong_phone = self.login(phone="201099000222")
        wrong_code = self.login(code="ZZZZZZ")
        crossed = self.login(code=other_enr.qr_token)  # my phone + someone else's child
        bodies = {r.content for r in (wrong_phone, wrong_code, crossed)}
        self.assertEqual({r.status_code for r in (wrong_phone, wrong_code, crossed)}, {400})
        self.assertEqual(len(bodies), 1, bodies)

    def test_a_child_who_has_not_activated_cannot_be_followed(self):
        self.student.is_active = False
        self.student.save(update_fields=["is_active"])
        self.assertEqual(self.login().status_code, 400)

    def test_a_deactivated_enrolment_is_refused(self):
        self.enr.is_active = False
        self.enr.save(update_fields=["is_active"])
        self.assertEqual(self.login().status_code, 400)

    def test_only_the_child_of_that_code_is_returned(self):
        sibling = self.make_student_in(self.env_a, "201555800003", "أخ")
        self.activate(sibling)
        Enrollment.objects.create(
            environment=self.env_a, student=sibling, grade=self.grade,
            student_name="أخ", parent_phone=GUARDIAN)
        data = self.login().json()
        self.assertEqual(len(data["children"]), 1)
        self.assertEqual(data["children"][0]["student_name"], "ابن")

    def test_guessing_codes_for_one_phone_is_throttled(self):
        statuses = [self.login(code=f"AAAA{i:02d}").status_code for i in range(12)]
        self.assertIn(429, statuses)

    def test_guessing_phones_for_one_code_is_throttled(self):
        code = self.enr.qr_token
        statuses = [self.login(phone=f"2010000000{i:02d}", code=code).status_code for i in range(12)]
        self.assertIn(429, statuses)
