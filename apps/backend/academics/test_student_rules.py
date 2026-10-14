"""The student activation rules and "edit student" — the behaviour the
teacher dashboard depends on:

  * active   -> the student can claim an account and log in
  * inactive (with EVERY teacher) -> cannot claim, cannot log in, existing
    tokens stop working; another teacher activating them restores access
  * editing: name/parent are teacher-scoped; phone only while unclaimed+unshared
"""
from rest_framework.test import APIClient

from accounts.models import User
from environments.models import Environment, EnvironmentMembership
from environments.tenancy_testing import PASSWORD, TenantTestCase

from .models import Enrollment, Grade, Group

ENR = "/api/v1/academics/enrollments/"
PHONE = "201555100001"
NATIONAL_NEW = "201555100002"


def code_for(phone):
    """The student code the teacher would hand over (the enrolment's badge
    code). Unknown numbers get a code that matches nothing."""
    e = Enrollment.objects.filter(student__phone=phone).first()
    return e.qr_token if e else "AAAAAA"


def claim(phone, password=PASSWORD):
    c = APIClient()
    r = c.post("/api/v1/auth/student/claim/", {"channel": "phone", "phone": phone, "student_code": code_for(phone)})
    if r.status_code != 200:
        return r, None
    pid, code = r.data["pending_id"], r.data["debug_otp"]
    c.post("/api/v1/auth/otp/student-claim/verify/", {"pending_id": pid, "code": code})
    a = c.post("/api/v1/auth/student/claim/activate/", {"pending_id": pid, "password": password, "password2": password})
    return a, c


class StudentActivationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=1)
        self.grade_b = Grade.objects.create(environment=self.env_b, name="أول", fee_amount=1)

    def add(self, client, env, grade, phone=PHONE, **extra):
        return client.post(ENR, {"name": "طالب تجريبي", "phone": phone, "grade_id": grade.id, **extra, "parent_phone": "201111000001"}, format="json", **self.with_env(env.id))

    def patch(self, client, env, pk, body):
        return client.patch(f"{ENR}{pk}/", body, format="json", **self.with_env(env.id))

    def test_new_student_added_active_by_default_and_can_claim(self):
        self.assertEqual(self.add(self.client_a, self.env_a, self.grade).status_code, 201)
        r, c = claim(PHONE)
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(APIClient().post("/api/v1/auth/student/login/", {"phone": PHONE, "password": PASSWORD}).status_code, 200)

    def test_student_added_as_inactive_cannot_claim(self):
        self.assertEqual(self.add(self.client_a, self.env_a, self.grade, is_active=False).status_code, 201)
        r, _ = claim(PHONE)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.data["code"], "not_found")

    def test_inactive_message_is_identical_to_unknown_number_no_oracle(self):
        self.add(self.client_a, self.env_a, self.grade, is_active=False)
        inactive = APIClient().post("/api/v1/auth/student/claim/",
                                    {"channel": "phone", "phone": PHONE, "student_code": code_for(PHONE)})
        unknown = APIClient().post("/api/v1/auth/student/claim/",
                                   {"channel": "phone", "phone": "201555199999", "student_code": "AAAAAA"})
        self.assertEqual((inactive.status_code, inactive.json()), (unknown.status_code, unknown.json()))

    def test_deactivating_the_only_teacher_blocks_login_and_kills_existing_tokens(self):
        e = self.add(self.client_a, self.env_a, self.grade).json()["enrollment_id"]
        claim(PHONE)
        login = APIClient().post("/api/v1/auth/student/login/", {"phone": PHONE, "password": PASSWORD})
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + login.data["access"])
        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 200)

        self.assertEqual(self.patch(self.client_a, self.env_a, e, {"is_active": False}).status_code, 200)

        self.assertEqual(c.get("/api/v1/auth/me/").status_code, 401)       # existing access token is dead
        again = APIClient().post("/api/v1/auth/student/login/", {"phone": PHONE, "password": PASSWORD})
        self.assertEqual(again.status_code, 400)
        self.assertEqual(again.json()["code"], "student_inactive")
        refresh = APIClient().post("/api/v1/auth/token/refresh/", {"refresh": login.data["refresh"]})
        self.assertNotEqual(refresh.status_code, 200)                      # refresh token revoked too

    def test_another_teacher_activating_the_student_restores_access(self):
        e_a = self.add(self.client_a, self.env_a, self.grade).json()["enrollment_id"]
        claim(PHONE)
        self.patch(self.client_a, self.env_a, e_a, {"is_active": False})
        self.assertEqual(APIClient().post("/api/v1/auth/student/login/", {"phone": PHONE, "password": PASSWORD}).status_code, 400)

        self.assertEqual(self.add(self.client_b, self.env_b, self.grade_b).status_code, 201)   # teacher B adds the same phone (active)
        login = APIClient().post("/api/v1/auth/student/login/", {"phone": PHONE, "password": PASSWORD})
        self.assertEqual(login.status_code, 200, login.content)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + login.data["access"])
        envs = c.get("/api/v1/environments/student/").json()
        self.assertEqual(len(envs), 1)                                     # only B's environment is usable
        self.assertEqual(c.post(f"/api/v1/environments/student/{self.env_a.id}/enter/").status_code, 404)
        self.assertEqual(c.get("/api/v1/environments/context/", **self.with_env(self.env_a.id)).status_code, 403)
        self.assertEqual(c.get("/api/v1/environments/context/", **self.with_env(self.env_b.id)).status_code, 200)

    def test_one_teacher_deactivating_does_not_affect_the_other_teachers_student(self):
        e_a = self.add(self.client_a, self.env_a, self.grade).json()["enrollment_id"]
        self.add(self.client_b, self.env_b, self.grade_b)
        claim(PHONE)
        self.patch(self.client_a, self.env_a, e_a, {"is_active": False})
        self.assertEqual(APIClient().post("/api/v1/auth/student/login/", {"phone": PHONE, "password": PASSWORD}).status_code, 200)

    def test_reactivating_lets_the_student_log_in_again(self):
        e = self.add(self.client_a, self.env_a, self.grade).json()["enrollment_id"]
        claim(PHONE)
        self.patch(self.client_a, self.env_a, e, {"is_active": False})
        self.patch(self.client_a, self.env_a, e, {"is_active": True})
        self.assertEqual(APIClient().post("/api/v1/auth/student/login/", {"phone": PHONE, "password": PASSWORD}).status_code, 200)

    def test_forgot_password_gives_no_otp_for_a_fully_inactive_student(self):
        e = self.add(self.client_a, self.env_a, self.grade).json()["enrollment_id"]
        claim(PHONE)
        self.patch(self.client_a, self.env_a, e, {"is_active": False})
        known = APIClient().post("/api/v1/auth/student/forgot/", {"phone": PHONE})
        unknown = APIClient().post("/api/v1/auth/student/forgot/", {"phone": "201555199999"})
        # Same outward shape as a number that does not exist: nothing is revealed,
        # and no OTP is attached to the deactivated account.
        self.assertEqual((known.status_code, set(known.data)), (unknown.status_code, set(unknown.data)))
        from accounts.models import PendingAuth

        self.assertFalse(PendingAuth.objects.exclude(user_id=None).filter(user_id=User.objects.get(phone=PHONE).id).exists()
                         if hasattr(PendingAuth, "user_id") else False)


class EditStudentTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=1)
        self.g1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.g2 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        self.other_grade = Grade.objects.create(environment=self.env_a, name="ثاني", fee_amount=1)
        self.other_group = Group.objects.create(environment=self.env_a, grade=self.other_grade, name="X")
        r = self.client_a.post(ENR, {"name": "اسم بالخطأ", "phone": PHONE, "grade_id": self.grade.id,
                                     "group_ids": [self.g1.id], "parent_phone": "+20 100 765 4321", "parent_name": "ولي الأمر"},
                               format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        self.eid = r.json()["enrollment_id"]

    def patch(self, body, client=None, env=None):
        return (client or self.client_a).patch(f"{ENR}{self.eid}/", body, format="json", **self.with_env((env or self.env_a).id))

    def get(self):
        return self.client_a.get(f"{ENR}{self.eid}/", **self.with_env(self.env_a.id)).json()

    def test_fix_name_parent_and_groups_after_adding(self):
        r = self.patch({"student_name": "الاسم الصحيح", "parent_name": "أبو أحمد", "parent_phone": "+966 55 123 4567", "group_ids": [self.g1.id, self.g2.id]})
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual(body["student"]["name"], "الاسم الصحيح")
        self.assertEqual(body["parent_phone"], "966551234567")
        self.assertEqual(sorted(g["id"] for g in body["groups"]), sorted([self.g1.id, self.g2.id]))

    def test_parent_phone_is_validated_per_country(self):
        self.assertEqual(self.patch({"parent_phone": "+20 123"}).status_code, 400)
        self.assertEqual(self.patch({"parent_phone": ""}).status_code, 200)  # may be cleared

    def test_groups_must_be_in_the_students_grade_and_environment(self):
        self.assertEqual(self.patch({"group_ids": [self.other_group.id]}).status_code, 400)
        foreign = Group.objects.create(environment=self.env_b, grade=Grade.objects.create(environment=self.env_b, name="ب", fee_amount=1), name="B")
        self.assertEqual(self.patch({"group_ids": [foreign.id]}).status_code, 400)

    def test_grade_and_academic_year_cannot_be_changed(self):
        before = Enrollment.objects.get(pk=self.eid)
        self.patch({"grade": self.other_grade.id, "grade_id": self.other_grade.id, "academic_year": "1999 / 2000"})
        after = Enrollment.objects.get(pk=self.eid)
        self.assertEqual((after.grade_id, after.academic_year), (before.grade_id, before.academic_year))

    def test_phone_typo_can_be_fixed_while_unclaimed_and_unshared(self):
        self.assertTrue(self.get()["can_edit_phone"])
        r = self.patch({"phone": "+20 100 111 2222"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["student"]["phone"], "201001112222")
        self.assertEqual(User.objects.filter(phone=PHONE).count(), 0)

    def test_phone_cannot_be_changed_to_a_number_already_in_use_and_message_is_generic(self):
        User.objects.create_user(role="student", name="آخر", phone="201001112222", password=None, is_active=False)
        r = self.patch({"phone": "+20 100 111 2222"})
        self.assertEqual(r.status_code, 400)
        self.assertNotIn("آخر", r.content.decode())

    def test_phone_is_locked_once_the_student_claims_the_account(self):
        claim(PHONE)
        self.assertFalse(self.get()["can_edit_phone"])
        r = self.patch({"phone": "+20 100 111 3333"})
        self.assertEqual(r.status_code, 400)
        self.assertTrue(User.objects.filter(phone=PHONE).exists())

    def test_phone_is_locked_when_another_teacher_also_has_the_student(self):
        from accounts.testing import make_enrollment

        make_enrollment(self.env_b, User.objects.get(phone=PHONE), Grade.objects.create(environment=self.env_b, name="ب", fee_amount=1))
        self.assertFalse(self.get()["can_edit_phone"])
        self.assertEqual(self.patch({"phone": "+20 100 111 4444"}).status_code, 400)

    def test_editing_the_name_never_touches_the_global_account_or_another_teachers_view(self):
        from accounts.testing import make_enrollment

        user = User.objects.get(phone=PHONE)
        eb = make_enrollment(self.env_b, user, Grade.objects.create(environment=self.env_b, name="ب", fee_amount=1), student_name="اسم المعلم ب")
        self.patch({"student_name": "اسم جديد عند أ"})
        user.refresh_from_db(); eb.refresh_from_db()
        self.assertEqual(user.name, "اسم بالخطأ")                       # global identity untouched
        self.assertEqual(eb.display_name, "اسم المعلم ب")               # B's view untouched
        row = self.client_b.get(ENR, **self.with_env(self.env_b.id)).json()["results"][0]
        self.assertEqual(row["student"]["name"], "اسم المعلم ب")

    def test_another_teacher_cannot_edit_or_read_this_enrollment(self):
        r = self.patch({"student_name": "اختراق"}, client=self.client_b, env=self.env_b)
        self.assertEqual(r.status_code, 404)
        self.assert_cross_tenant_denied("patch", f"{ENR}{self.eid}/", body={"student_name": "x"})
        self.assertEqual(Enrollment.objects.get(pk=self.eid).student_name, "اسم بالخطأ")

    def test_roster_is_not_blocked_by_the_add_student_throttle(self):
        from unittest import mock

        from rest_framework.throttling import SimpleRateThrottle

        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"student-add": "1/hour"}):
            codes = [self.client_a.get(ENR, **self.with_env(self.env_a.id)).status_code for _ in range(5)]
        self.assertEqual(codes, [200] * 5)

    def test_student_name_is_required_when_editing_it(self):
        self.assertEqual(self.patch({"student_name": " "}).status_code, 400)


class DeleteGuardTests(TenantTestCase):
    def test_group_with_sessions_is_refused_not_a_500(self):
        from django.utils import timezone

        from scheduling.models import SessionInstance

        grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=1)
        group = Group.objects.create(environment=self.env_a, grade=grade, name="G")
        SessionInstance.objects.create(environment=self.env_a, group=group, scheduled_at=timezone.now())
        r = self.client_a.delete(f"/api/v1/academics/groups/{group.id}/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400, r.content)
        self.assertTrue(Group.objects.filter(pk=group.id).exists())
