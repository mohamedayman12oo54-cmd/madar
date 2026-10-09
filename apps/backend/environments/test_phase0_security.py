"""Phase 0 / S5 — enrolling a student must not leak anything about GLOBAL
student accounts across teachers, and must not become a phone/account oracle.

Ported from the retired `/environments/students/` endpoint to its replacement,
`POST /api/v1/academics/enrollments/` (the Enrollment IS the student's presence
in an environment). The privacy/throttling contract is unchanged, so every
assertion below is preserved; only the transport moved. The target environment
is resolved server-side from the active-environment header, never from the body
— which is itself asserted here.
"""
import json
from unittest import mock

from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from academics.models import Enrollment, Grade
from accounts.models import User
from environments.models import Environment, EnvironmentMembership
from environments.tenancy import ACTIVE_ENVIRONMENT_HEADER
from accounts.testing import TestCase

PW = "Str0ng!Pass"
URL = "/api/v1/academics/enrollments/"
REAL_NAME = "اسم الطالب الحقيقي السري"
_HEADER_KWARG = "HTTP_" + ACTIVE_ENVIRONMENT_HEADER.upper().replace("-", "_")


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
        self.grade_a = Grade.objects.create(environment=self.env_a, name="أول")
        self.grade_b = Grade.objects.create(environment=self.env_b, name="أول")
        # Teacher A's ACTIVE student and an UNCLAIMED pre-registered one.
        self.active = User.objects.create_user(role="student", name=REAL_NAME, phone="201555000001",
                                               password=PW, is_active=True, is_verified=True)
        self.unclaimed = User.objects.create_user(role="student", name=REAL_NAME + " 2", phone="201555000002",
                                                  password=None, is_active=False)
        for s in (self.active, self.unclaimed):
            EnvironmentMembership.objects.create(user=s, environment=self.env_a, role="student")
            Enrollment.objects.create(environment=self.env_a, student=s, grade=self.grade_a)
        self.cb = client_for("b@example.com")

    def add(self, phone, name="اسم كتبه المعلم ب", client=None, env=None, grade=None):
        env = env or self.env_b
        return (client or self.cb).post(
            URL,
            {"name": name, "phone": phone, "grade_id": (grade or self.grade_b).id,
             # Deliberately also claim another environment in the BODY: it must
             # be ignored in favour of the server-resolved header context.
             "environment_id": self.env_a.id, "parent_phone": "201111000001"},
            **{_HEADER_KWARG: str(env.id)},
        )

    def test_response_never_contains_the_existing_accounts_data(self):
        """regression: response returned the existing account's real name,
        `already_claimed` and the global user id."""
        for phone in (self.active.phone, self.unclaimed.phone):
            with self.subTest(phone=phone):
                r = self.add(phone)
                self.assertEqual(r.status_code, 201, r.content)
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

    def test_enrollment_created_only_in_callers_own_environment(self):
        r = self.add(self.active.phone)
        enr = Enrollment.objects.get(pk=r.json()["enrollment_id"])
        self.assertEqual(enr.environment_id, self.env_b.id)
        self.assertEqual(enr.student_id, self.active.id)
        # and A's own roster is untouched
        self.assertEqual(Enrollment.objects.filter(environment=self.env_a).count(), 2)

    def test_body_environment_id_cannot_redirect_the_write(self):
        """The body claims env A; the header says env B. The server must use
        the header and never write into another teacher's environment."""
        before = Enrollment.objects.filter(environment=self.env_a).count()
        r = self.add("201555777777")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Enrollment.objects.filter(environment=self.env_a).count(), before)
        self.assertEqual(Enrollment.objects.get(pk=r.json()["enrollment_id"]).environment_id, self.env_b.id)

    def test_cannot_add_into_another_teachers_environment(self):
        """B points the active-environment header at A's environment."""
        r = self.cb.post(
            URL, {"name": "x", "phone": "201555777778", "grade_id": self.grade_a.id, "parent_phone": "201111000001"},
            **{_HEADER_KWARG: str(self.env_a.id)},
        )
        self.assertEqual(r.status_code, 403, r.content)
        self.assertFalse(User.objects.filter(phone="201555777778").exists())

    def test_grade_from_another_environment_is_rejected(self):
        r = self.cb.post(
            URL, {"name": "x", "phone": "201555777779", "grade_id": self.grade_a.id, "parent_phone": "201111000001"},
            **{_HEADER_KWARG: str(self.env_b.id)},
        )
        self.assertEqual(r.status_code, 400, r.content)
        self.assertFalse(User.objects.filter(phone="201555777779").exists())

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
        self.assertEqual(first.json()["enrollment_id"], second.json()["enrollment_id"])

    def test_requires_teacher_authentication(self):
        anon = APIClient()
        r = anon.post(URL, {"name": "x", "phone": "201555000009", "grade_id": self.grade_b.id, "parent_phone": "201111000001"},
                      **{_HEADER_KWARG: str(self.env_b.id)})
        self.assertEqual(r.status_code, 401, r.content)
        student = User.objects.create_user(role="student", name="s", phone="201555000010", password=PW, is_active=True, is_verified=True)
        EnvironmentMembership.objects.create(user=student, environment=self.env_b, role="student")
        # A student can only log in while they have an ACTIVE enrollment.
        Enrollment.objects.create(environment=self.env_b, student=student, grade=self.grade_b)
        c = APIClient()
        tok = c.post("/api/v1/auth/student/login/", {"phone": student.phone, "password": PW}).data["access"]
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        r = c.post(URL, {"name": "x", "phone": "201555000011", "grade_id": self.grade_b.id, "parent_phone": "201111000001"},
                   **{_HEADER_KWARG: str(self.env_b.id)})
        self.assertEqual(r.status_code, 403, r.content)

    def test_add_student_is_rate_limited_per_teacher(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"student-add": "3/hour"}):
            codes = [self.add(f"2015558000{i:02d}").status_code for i in range(4)]
        self.assertEqual(codes, [201, 201, 201, 429])

    def test_a_real_class_of_students_is_not_throttled(self):
        codes = {self.add(f"2015559{i:05d}").status_code for i in range(40)}
        self.assertEqual(codes, {201})

    def test_reading_the_roster_is_not_blocked_by_the_add_budget(self):
        """GET must not consume/trip the student-add throttle."""
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"student-add": "2/hour"}):
            for i in range(2):
                self.add(f"2015556100{i:02d}")
            self.assertEqual(self.add("201555610099").status_code, 429)
            r = self.cb.get(URL, **{_HEADER_KWARG: str(self.env_b.id)})
            self.assertEqual(r.status_code, 200, r.content)

    def test_throttle_is_per_teacher_not_shared(self):
        c_a = client_for("a@example.com")
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"student-add": "2/hour"}):
            for i in range(2):
                self.add(f"2015557000{i:02d}")
            self.assertEqual(self.add("201555700099").status_code, 429)
            ok = self.add("201555700098", client=c_a, env=self.env_a, grade=self.grade_a)
            self.assertEqual(ok.status_code, 201, ok.content)
