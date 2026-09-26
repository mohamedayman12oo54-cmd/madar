"""
Phase 2 — Enrollment: creation (find-or-create student), list/search/filter,
update (immutability of grade/academic_year), and cross-tenant isolation.

This supersedes environments/test_phase0_security.py (AddStudentDisclosureTests,
deleted — it tested AddStudentView, which this phase removes) and the original
uploaded AddStudentTests class in environments/tests.py (trimmed for the same
reason). Every protection those covered is re-verified here against the new
endpoint, plus the header-based tenancy fix.
"""
import json
from unittest import mock

from rest_framework.test import APIClient
from rest_framework.throttling import SimpleRateThrottle

from accounts.models import User
from environments.models import EnvironmentMembership
from environments.tenancy_testing import TenantTestCase

from .models import Enrollment, Grade, Group

ENROLL_URL = "/api/v1/academics/enrollments/"
REAL_NAME = "اسم الطالب الحقيقي السري"


def enrollment_url(pk):
    return f"{ENROLL_URL}{pk}/"


def _second_environment_for(owner, name):
    from environments.models import Environment, EnvironmentMembership
    env = Environment.objects.create(owner=owner, name=name)
    EnvironmentMembership.objects.create(user=owner, environment=env, role=EnvironmentMembership.Role.OWNER)
    return env


class EnrollmentCreateTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade_a = Grade.objects.create(environment=self.env_a, name="الصف الأول")
        self.grade_b = Grade.objects.create(environment=self.env_b, name="الصف الأول")

    def enroll_a(self, **overrides):
        body = {"name": "طالب جديد", "phone": "201060000001", "grade_id": self.grade_a.id}
        body.update(overrides)
        return self.client_a.post(ENROLL_URL, body, **self.with_env(self.env_a.id))

    def test_creates_a_new_pre_registered_student(self):
        r = self.enroll_a()
        self.assertEqual(r.status_code, 201, r.content)
        user = User.objects.get(phone="201060000001")
        self.assertEqual(user.role, "student")
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())
        enrollment = Enrollment.objects.get(pk=r.json()["enrollment_id"])
        self.assertEqual(enrollment.environment_id, self.env_a.id)
        self.assertEqual(enrollment.grade_id, self.grade_a.id)
        self.assertTrue(EnvironmentMembership.objects.filter(user=user, environment=self.env_a, role="student").exists())

    def test_academic_year_is_stamped_automatically(self):
        from environments.models import current_academic_year
        r = self.enroll_a()
        self.assertEqual(r.json()["academic_year"], current_academic_year())

    def test_same_student_reused_across_two_of_the_same_teachers_environments(self):
        env_a2 = _second_environment_for(self.teacher_a, "بيئة أ الثانية")
        grade_a2 = Grade.objects.create(environment=env_a2, name="ابتدائي")
        self.enroll_a()
        r2 = self.client_a.post(
            ENROLL_URL, {"name": "طالب جديد", "phone": "201060000001", "grade_id": grade_a2.id},
            **self.with_env(env_a2.id),
        )
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(User.objects.filter(phone="201060000001").count(), 1)
        self.assertEqual(EnvironmentMembership.objects.filter(user__phone="201060000001").count(), 2)
        self.assertEqual(Enrollment.objects.filter(student__phone="201060000001").count(), 2)

    def test_there_is_no_environment_id_field_at_all(self):
        """The old vulnerability class (Phase 0/S5: a body-supplied
        environment_id) is now structurally impossible — there is nothing in
        the payload for it. Sending one anyway has zero effect: the header
        alone decides the tenant."""
        r = self.client_b.post(
            ENROLL_URL,
            {"name": "X", "phone": "201060000099", "grade_id": self.grade_a.id, "environment_id": self.env_a.id},
            **self.with_env(self.env_b.id),
        )
        # grade_id belongs to env_a, not env_b (the header) -> rejected on THAT basis
        self.assertEqual(r.status_code, 400)
        self.assertIn("grade_id", r.json()["fields"])

    def test_cannot_enroll_using_another_teachers_grade_even_with_own_header(self):
        r = self.client_b.post(
            ENROLL_URL, {"name": "X", "phone": "201060000098", "grade_id": self.grade_a.id},
            **self.with_env(self.env_b.id),
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(User.objects.filter(phone="201060000098").exists())

    def test_group_must_belong_to_the_same_grade(self):
        other_grade = Grade.objects.create(environment=self.env_a, name="آخر")
        other_group = Group.objects.create(environment=self.env_a, grade=other_grade, name="G")
        r = self.enroll_a(group_id=other_group.id)
        self.assertEqual(r.status_code, 400)
        self.assertIn("group_id", r.json()["fields"])

    def test_group_in_same_grade_is_accepted(self):
        group = Group.objects.create(environment=self.env_a, grade=self.grade_a, name="G")
        r = self.enroll_a(group_id=group.id)
        self.assertEqual(r.status_code, 201)
        self.assertEqual(Enrollment.objects.get(pk=r.json()["enrollment_id"]).group_id, group.id)

    def test_non_student_phone_gets_one_generic_message(self):
        r = self.enroll_a(phone=self.teacher_a.phone)
        self.assertEqual(r.status_code, 400)
        text = json.dumps(r.json(), ensure_ascii=False)
        self.assertIn("لا يمكن إضافة هذا الرقم كطالب.", text)
        self.assertNotIn("نوع آخر", text)
        self.assertNotIn("teacher", text.lower())

    # -- disclosure: the exact Phase 0 / S5 protections, re-verified here --
    def test_response_never_reveals_another_teachers_students_real_identity(self):
        existing = User.objects.create_user(role="student", name=REAL_NAME, phone="201070000001", password=None, is_active=False)
        EnvironmentMembership.objects.create(user=existing, environment=self.env_b, role="student")
        r = self.enroll_a(phone="201070000001", name="اسم كتبه المعلم أ")
        self.assertEqual(r.status_code, 201)
        body = json.dumps(r.json(), ensure_ascii=False)
        self.assertNotIn(REAL_NAME, body)
        self.assertEqual(r.json()["name"], "اسم كتبه المعلم أ")
        existing.refresh_from_db()
        self.assertEqual(existing.name, REAL_NAME)  # global name never overwritten

    def test_existing_and_brand_new_phones_are_indistinguishable_in_response_shape(self):
        existing = User.objects.create_user(role="student", name="X", phone="201070000002", password=None, is_active=False)
        shapes = []
        for phone in (existing.phone, "201070000099"):
            r = self.enroll_a(phone=phone, name="اسم")
            shapes.append((r.status_code, sorted(r.json().keys())))
        self.assertEqual(len(set(map(str, shapes))), 1, shapes)

    def test_requires_teacher_owner_role(self):
        anon = APIClient()
        self.assertEqual(anon.post(ENROLL_URL, {}, **self.with_env(self.env_a.id)).status_code, 401)

    def test_rate_limited_per_teacher(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"student-add": "2/hour"}):
            codes = [
                self.enroll_a(phone=f"20106000010{i}").status_code for i in range(3)
            ]
        self.assertEqual(codes, [201, 201, 429])

    def test_throttle_is_per_teacher_not_shared(self):
        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"student-add": "1/hour"}):
            self.enroll_a(phone="201060000201")
            self.assertEqual(self.enroll_a(phone="201060000202").status_code, 429)
            r = self.client_b.post(
                ENROLL_URL, {"name": "x", "phone": "201060000203", "grade_id": self.grade_b.id},
                **self.with_env(self.env_b.id),
            )
            self.assertEqual(r.status_code, 201)


class EnrollmentListTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade_a = Grade.objects.create(environment=self.env_a, name="أول")
        self.group_a = Group.objects.create(environment=self.env_a, grade=self.grade_a, name="G1")
        self.s1 = self.make_student_in(self.env_a, "201080000001", name="أحمد محمد")
        self.s2 = self.make_student_in(self.env_a, "201080000002", name="سارة علي")
        Enrollment.objects.create(environment=self.env_a, student=self.s1, grade=self.grade_a, group=self.group_a)
        Enrollment.objects.create(environment=self.env_a, student=self.s2, grade=self.grade_a)
        # a decoy in Teacher B's environment
        grade_b = Grade.objects.create(environment=self.env_b, name="أول")
        s3 = self.make_student_in(self.env_b, "201080000003", name="Other Teacher's Student")
        Enrollment.objects.create(environment=self.env_b, student=s3, grade=grade_b)

    def _items(self, r):
        data = r.json()
        return data["results"] if isinstance(data, dict) and "results" in data else data

    def test_list_is_scoped_to_active_environment(self):
        r = self.client_a.get(ENROLL_URL, **self.with_env(self.env_a.id))
        names = {e["student"]["name"] for e in self._items(r)}
        self.assertEqual(names, {"أحمد محمد", "سارة علي"})

    def test_search_by_name(self):
        r = self.client_a.get(f"{ENROLL_URL}?search=سارة", **self.with_env(self.env_a.id))
        names = {e["student"]["name"] for e in self._items(r)}
        self.assertEqual(names, {"سارة علي"})

    def test_search_by_phone(self):
        r = self.client_a.get(f"{ENROLL_URL}?search=80000001", **self.with_env(self.env_a.id))
        self.assertEqual(len(self._items(r)), 1)

    def test_filter_by_group_id(self):
        r = self.client_a.get(f"{ENROLL_URL}?group_id={self.group_a.id}", **self.with_env(self.env_a.id))
        names = {e["student"]["name"] for e in self._items(r)}
        self.assertEqual(names, {"أحمد محمد"})

    def test_filter_by_is_active(self):
        Enrollment.objects.filter(student=self.s2).update(is_active=False)
        r = self.client_a.get(f"{ENROLL_URL}?is_active=false", **self.with_env(self.env_a.id))
        names = {e["student"]["name"] for e in self._items(r)}
        self.assertEqual(names, {"سارة علي"})

    def test_response_includes_grade_fee_for_financial_summaries(self):
        Grade.objects.filter(pk=self.grade_a.pk).update(fee_amount="350.00")
        r = self.client_a.get(ENROLL_URL, **self.with_env(self.env_a.id))
        fees = {e["grade"]["fee_amount"] for e in self._items(r)}
        self.assertEqual(fees, {"350.00"})


class EnrollmentDetailTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade_a = Grade.objects.create(environment=self.env_a, name="أول")
        self.group_a1 = Group.objects.create(environment=self.env_a, grade=self.grade_a, name="G1")
        self.group_a2 = Group.objects.create(environment=self.env_a, grade=self.grade_a, name="G2")
        self.other_grade = Grade.objects.create(environment=self.env_a, name="آخر")
        self.student = self.make_student_in(self.env_a, "201090000001", name="طالب")
        self.enrollment = Enrollment.objects.create(
            environment=self.env_a, student=self.student, grade=self.grade_a, group=self.group_a1,
        )

    def test_move_to_another_group_in_the_same_grade(self):
        r = self.client_a.patch(enrollment_url(self.enrollment.id), {"group": self.group_a2.id}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.group_id, self.group_a2.id)

    def test_cannot_move_to_a_group_from_a_different_grade(self):
        other_group = Group.objects.create(environment=self.env_a, grade=self.other_grade, name="X")
        r = self.client_a.patch(enrollment_url(self.enrollment.id), {"group": other_group.id}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_deactivate_and_reactivate(self):
        r = self.client_a.patch(enrollment_url(self.enrollment.id), {"is_active": False}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        self.enrollment.refresh_from_db()
        self.assertFalse(self.enrollment.is_active)

    def test_grade_field_is_not_accepted_on_update(self):
        other_grade_id = self.other_grade.id
        r = self.client_a.patch(enrollment_url(self.enrollment.id), {"grade": other_grade_id}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)  # accepted as a no-op — "grade" isn't a field on the update serializer
        self.enrollment.refresh_from_db()
        self.assertEqual(self.enrollment.grade_id, self.grade_a.id)  # unchanged

    def test_academic_year_field_is_not_accepted_on_update(self):
        r = self.client_a.patch(enrollment_url(self.enrollment.id), {"academic_year": "1999 / 2000"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        self.enrollment.refresh_from_db()
        self.assertNotEqual(self.enrollment.academic_year, "1999 / 2000")

    def test_model_level_guard_blocks_changing_grade_directly_via_the_orm(self):
        """Defense-in-depth below the API layer — proven independently."""
        from django.core.exceptions import ValidationError
        self.enrollment.grade = self.other_grade
        with self.assertRaises(ValidationError):
            self.enrollment.save()

    def test_cannot_delete_enrollment(self):
        r = self.client_a.delete(enrollment_url(self.enrollment.id), **self.with_env(self.env_a.id))
        self.assertIn(r.status_code, (403, 405))
        self.assertTrue(Enrollment.objects.filter(pk=self.enrollment.id).exists())

    def test_cannot_read_or_update_another_teachers_enrollment(self):
        self.assert_cross_tenant_denied("get", enrollment_url(self.enrollment.id))
        self.assert_cross_tenant_denied("patch", enrollment_url(self.enrollment.id), body={"is_active": False})


