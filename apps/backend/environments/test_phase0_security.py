"""Phase 0 / S5 — AddStudentView must not leak anything about GLOBAL student
accounts across teachers, and must not become a phone/account oracle."""
import json
from unittest import mock

from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from accounts.models import User
from accounts.testing import TestCase
from environments.models import Environment, EnvironmentMembership

PW = "Str0ng!Pass"
URL = "/api/v1/environments/students/"
REAL_NAME = "اسم الطالب الحقيقي السري"


def teacher(email, phone, env_name):
    u = User.objects.create_user(role=User.Role.TEACHER, name=email, email=email, phone=phone, password=PW, is_active=True)
    env = Environment.objects.create(owner=u, name=env_name)
    EnvironmentMembership.objects.create(user=u, environment=env, role="owner")
    return u, env


def client_for(email):
    c = APIClient()
    r = c.post("/api/v1/auth/teacher/login/", {"identifier": email, "password": PW})
    c.credentials(HTTP_AUTHORIZATION="Bearer " + r.data["access"])
    return c


class AddStudentDisclosureTests(TestCase):
    def setUp(self):
        self.a, self.env_a = teacher("a@example.com", "201010000001", "A")
        self.b, self.env_b = teacher("b@example.com", "201010000002", "B")
        # Teacher A's ACTIVE student and an UNCLAIMED pre-registered one.
        self.active = User.objects.create_user(role="student", name=REAL_NAME, phone="201555000001",
                                               password=PW, is_active=True, is_verified=True)
        self.unclaimed = User.objects.create_user(role="student", name=REAL_NAME + " 2", phone="201555000002",
                                                  password=None, is_active=False)
        for s in (self.active, self.unclaimed):
            EnvironmentMembership.objects.create(user=s, environment=self.env_a, role="student")
        self.cb = client_for("b@example.com")

    def add(self, phone, name="اسم كتبه المعلم ب"):
        return self.cb.post(URL, {"name": name, "phone": phone, "environment_id": self.env_b.id})

    def test_response_never_contains_the_existing_accounts_data(self):
        """regression: response returned the existing account's real name,
        `already_claimed` and the global user id."""
        for phone in (self.active.phone, self.unclaimed.phone):
            with self.subTest(phone=phone):
                r = self.add(phone)
                self.assertEqual(r.status_code, 201)
                body = json.dumps(r.json(), ensure_ascii=False)
                self.assertNotIn(REAL_NAME, body)
                self.assertNotIn("already_claimed", r.json())
                self.assertNotIn("student_id", r.json())
                self.assertEqual(r.json()["name"], "اسم كتبه المعلم ب")  # only echoes what B typed

    def test_existing_and_brand_new_phones_are_indistinguishable(self):
        shapes = []
        for phone in (self.active.phone, self.unclaimed.phone, "201555999999"):  # last one is new
            r = self.add(phone)
            shapes.append((r.status_code, sorted(r.json().keys())))
        self.assertEqual(len(set(map(str, shapes))), 1, shapes)

    def test_global_name_is_not_overwritten_by_another_teacher(self):
        self.add(self.active.phone, name="اسم مزوّر")
        self.active.refresh_from_db()
        self.assertEqual(self.active.name, REAL_NAME)

    def test_membership_created_only_in_callers_own_environment(self):
        r = self.add(self.active.phone)
        m = EnvironmentMembership.objects.get(pk=r.json()["membership_id"])
        self.assertEqual(m.environment_id, self.env_b.id)
        self.assertEqual(m.user_id, self.active.id)
        # and A's own roster is untouched
        self.assertEqual(EnvironmentMembership.objects.filter(environment=self.env_a, role="student").count(), 2)

    def test_cannot_add_into_another_teachers_environment(self):
        r = self.cb.post(URL, {"name": "x", "phone": "201555777777", "environment_id": self.env_a.id})
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(phone="201555777777").exists())

    def test_non_student_phone_gets_one_generic_message_without_role_hint(self):
        r = self.add(self.a.phone)  # a teacher's phone
        self.assertEqual(r.status_code, 400)
        text = json.dumps(r.json(), ensure_ascii=False)
        self.assertIn("لا يمكن إضافة هذا الرقم كطالب.", text)
        self.assertNotIn("نوع آخر", text)  # old message revealed "registered with another account type"
        self.assertNotIn("teacher", text.lower())

    def test_adding_same_phone_twice_is_idempotent_for_the_callers_own_roster(self):
        first = self.add("201555666666")
        second = self.add("201555666666")
        self.assertEqual((first.status_code, second.status_code), (201, 200))
        self.assertEqual(first.json()["membership_id"], second.json()["membership_id"])

    def test_requires_teacher_authentication(self):
        anon = APIClient()
        self.assertEqual(anon.post(URL, {"name": "x", "phone": "201555000009", "environment_id": self.env_b.id}).status_code, 401)
        student = User.objects.create_user(role="student", name="s", phone="201555000010", password=PW, is_active=True)
        c = APIClient()
        tok = c.post("/api/v1/auth/student/login/", {"phone": student.phone, "password": PW}).data["access"]
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        self.assertEqual(c.post(URL, {"name": "x", "phone": "201555000011", "environment_id": self.env_b.id}).status_code, 403)

    def test_add_student_is_rate_limited_per_teacher(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"student-add": "3/hour"}):
            codes = [self.add(f"2015558000{i:02d}").status_code for i in range(4)]
        self.assertEqual(codes, [201, 201, 201, 429])

    def test_a_real_class_of_students_is_not_throttled(self):
        codes = {self.add(f"2015559{i:03d}").status_code for i in range(40)}
        self.assertEqual(codes, {201})

    def test_throttle_is_per_teacher_not_shared(self):
        c_a = client_for("a@example.com")
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"student-add": "2/hour"}):
            for i in range(2):
                self.add(f"2015557000{i:02d}")
            self.assertEqual(self.add("201555700099").status_code, 429)
            ok = c_a.post(URL, {"name": "x", "phone": "201555700098", "environment_id": self.env_a.id})
            self.assertEqual(ok.status_code, 201)
