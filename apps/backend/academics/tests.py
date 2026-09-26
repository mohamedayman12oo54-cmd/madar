"""Phase 2 — Grade and Group: CRUD, ownership rules, cross-tenant isolation."""
from django.core.exceptions import ValidationError as DjangoValidationError

from environments.tenancy_testing import TenantTestCase

from .models import Grade, Group

GRADES_URL = "/api/v1/academics/grades/"
GROUPS_URL = "/api/v1/academics/groups/"


def grade_url(pk):
    return f"{GRADES_URL}{pk}/"


def group_url(pk):
    return f"{GROUPS_URL}{pk}/"


class GradeTests(TenantTestCase):
    def test_create_grade(self):
        r = self.client_a.post(GRADES_URL, {"name": "الصف الأول الثانوي", "fee_amount": "500.00"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual(body["name"], "الصف الأول الثانوي")
        self.assertEqual(body["fee_amount"], "500.00")
        grade = Grade.objects.get(pk=body["id"])
        self.assertEqual(grade.environment_id, self.env_a.id)

    def test_negative_fee_rejected(self):
        r = self.client_a.post(GRADES_URL, {"name": "X", "fee_amount": "-1"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)
        self.assertIn("fee_amount", r.json()["fields"])

    def test_blank_name_rejected(self):
        r = self.client_a.post(GRADES_URL, {"name": "   ", "fee_amount": "0"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_duplicate_name_in_same_environment_rejected(self):
        self.client_a.post(GRADES_URL, {"name": "الصف الأول", "fee_amount": "0"}, **self.with_env(self.env_a.id))
        r = self.client_a.post(GRADES_URL, {"name": "الصف الأول", "fee_amount": "0"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Grade.objects.filter(environment=self.env_a, name="الصف الأول").count(), 1)

    def test_same_name_allowed_in_different_environments(self):
        self.client_a.post(GRADES_URL, {"name": "الصف الأول", "fee_amount": "0"}, **self.with_env(self.env_a.id))
        r = self.client_b.post(GRADES_URL, {"name": "الصف الأول", "fee_amount": "0"}, **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 201)

    def test_list_is_scoped_to_active_environment(self):
        Grade.objects.create(environment=self.env_a, name="A1")
        Grade.objects.create(environment=self.env_b, name="B1")
        r = self.client_a.get(GRADES_URL, **self.with_env(self.env_a.id))
        names = [g["name"] for g in r.json()["results"]] if "results" in r.json() else [g["name"] for g in r.json()]
        self.assertEqual(names, ["A1"])

    def test_cannot_read_another_teachers_grade(self):
        grade = Grade.objects.create(environment=self.env_a, name="سري")
        self.assert_cross_tenant_denied("get", grade_url(grade.id))

    def test_cannot_update_another_teachers_grade(self):
        grade = Grade.objects.create(environment=self.env_a, name="سري")
        self.assert_cross_tenant_denied("patch", grade_url(grade.id), body={"name": "تعديل"})
        grade.refresh_from_db()
        self.assertEqual(grade.name, "سري")

    def test_cannot_delete_another_teachers_grade(self):
        grade = Grade.objects.create(environment=self.env_a, name="سري")
        self.assert_cross_tenant_denied("delete", grade_url(grade.id))
        self.assertTrue(Grade.objects.filter(pk=grade.id).exists())

    def test_grade_id_in_url_cannot_be_reached_via_own_valid_header(self):
        """Even with a VALID header for env_b, Teacher B naming env_a's grade
        id in the URL gets 404 (filtered out by TenantScopedQuerySetMixin),
        not the grade's data."""
        grade = Grade.objects.create(environment=self.env_a, name="سري")
        r = self.client_b.get(grade_url(grade.id), **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)

    def test_cannot_delete_grade_with_groups(self):
        grade = Grade.objects.create(environment=self.env_a, name="G")
        Group.objects.create(environment=self.env_a, grade=grade, name="Group 1")
        r = self.client_a.delete(grade_url(grade.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)
        self.assertTrue(Grade.objects.filter(pk=grade.id).exists())

    def test_delete_grade_with_no_dependents_succeeds(self):
        grade = Grade.objects.create(environment=self.env_a, name="G")
        r = self.client_a.delete(grade_url(grade.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 204)
        self.assertFalse(Grade.objects.filter(pk=grade.id).exists())

    def test_student_member_cannot_manage_grades(self):
        student = self.make_student_in(self.env_a, "201050000001")
        student.set_password("Str0ng!Pass")
        student.is_active = True
        student.save()
        from rest_framework.test import APIClient
        c = APIClient()
        tok = c.post("/api/v1/auth/student/login/", {"phone": student.phone, "password": "Str0ng!Pass"}).data["access"]
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        r = c.get(GRADES_URL, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 403)

    def test_requires_active_environment_header(self):
        r = self.client_a.get(GRADES_URL)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "environment_required")


class GroupTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade_a = Grade.objects.create(environment=self.env_a, name="الصف الأول")
        self.grade_b = Grade.objects.create(environment=self.env_b, name="الصف الأول")

    def test_create_group(self):
        r = self.client_a.post(GROUPS_URL, {"name": "مجموعة السبت", "grade_id": self.grade_a.id}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual(body["grade_id"], self.grade_a.id)
        self.assertEqual(body["student_count"], 0)

    def test_cannot_create_group_under_another_environments_grade(self):
        """The grade_id itself is real — just not the caller's. Must be
        rejected the same way an entirely made-up id would be."""
        r = self.client_a.post(GROUPS_URL, {"name": "X", "grade_id": self.grade_b.id}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(Group.objects.filter(name="X").exists())

    def test_duplicate_group_name_within_same_grade_rejected(self):
        self.client_a.post(GROUPS_URL, {"name": "دفعة 1", "grade_id": self.grade_a.id}, **self.with_env(self.env_a.id))
        r = self.client_a.post(GROUPS_URL, {"name": "دفعة 1", "grade_id": self.grade_a.id}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_same_group_name_allowed_under_a_different_grade(self):
        grade2 = Grade.objects.create(environment=self.env_a, name="الصف الثاني")
        self.client_a.post(GROUPS_URL, {"name": "دفعة 1", "grade_id": self.grade_a.id}, **self.with_env(self.env_a.id))
        r = self.client_a.post(GROUPS_URL, {"name": "دفعة 1", "grade_id": grade2.id}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201)

    def test_filter_by_grade_id(self):
        grade2 = Grade.objects.create(environment=self.env_a, name="الصف الثاني")
        Group.objects.create(environment=self.env_a, grade=self.grade_a, name="G1")
        Group.objects.create(environment=self.env_a, grade=grade2, name="G2")
        r = self.client_a.get(f"{GROUPS_URL}?grade_id={self.grade_a.id}", **self.with_env(self.env_a.id))
        data = r.json()["results"] if "results" in r.json() else r.json()
        self.assertEqual([g["name"] for g in data], ["G1"])

    def test_rename_group_does_not_require_or_accept_grade_id(self):
        group = Group.objects.create(environment=self.env_a, grade=self.grade_a, name="Old")
        r = self.client_a.patch(group_url(group.id), {"name": "New"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        group.refresh_from_db()
        self.assertEqual(group.name, "New")
        self.assertEqual(group.grade_id, self.grade_a.id)

    def test_grade_id_sent_on_rename_is_silently_ignored_not_applied(self):
        grade2 = Grade.objects.create(environment=self.env_a, name="آخر")
        group = Group.objects.create(environment=self.env_a, grade=self.grade_a, name="G")
        r = self.client_a.patch(group_url(group.id), {"name": "G", "grade_id": grade2.id}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        group.refresh_from_db()
        self.assertEqual(group.grade_id, self.grade_a.id)  # unchanged

    def test_cannot_access_another_teachers_group(self):
        group = Group.objects.create(environment=self.env_a, grade=self.grade_a, name="سري")
        self.assert_cross_tenant_denied("get", group_url(group.id))
        self.assert_cross_tenant_denied("patch", group_url(group.id), body={"name": "x"})
        self.assert_cross_tenant_denied("delete", group_url(group.id))

    def test_cannot_delete_group_with_students(self):
        from academics.models import Enrollment
        group = Group.objects.create(environment=self.env_a, grade=self.grade_a, name="G")
        student = self.make_student_in(self.env_a, "201050000002")
        Enrollment.objects.create(environment=self.env_a, student=student, grade=self.grade_a, group=group)
        r = self.client_a.delete(group_url(group.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)
        self.assertTrue(Group.objects.filter(pk=group.id).exists())

    def test_model_level_clean_rejects_grade_from_a_different_environment(self):
        """Defense-in-depth: even bypassing the serializer, .clean() catches
        a Group/Grade environment mismatch."""
        group = Group(environment=self.env_a, grade=self.grade_b, name="X")
        with self.assertRaises(DjangoValidationError):
            group.clean()
