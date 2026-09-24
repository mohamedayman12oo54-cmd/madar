from accounts.testing import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from .models import Environment, EnvironmentMembership

VALID_PW = "Str0ng!Pass"


def auth(client, resp):
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")


class TeacherEnvironmentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="Ahmed", email="t1@example.com", phone="201010101010",
            password=VALID_PW, is_active=True,
        )
        self.other_teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="Sara", email="t2@example.com", phone="201020202020",
            password=VALID_PW, is_active=True,
        )
        self.env1 = Environment.objects.create(owner=self.teacher, name="الصف الثالث")
        self.env2 = Environment.objects.create(owner=self.teacher, name="الصف الثاني")
        self.other_env = Environment.objects.create(owner=self.other_teacher, name="بيئة أخرى")
        EnvironmentMembership.objects.create(user=self.teacher, environment=self.env1, role="owner")
        EnvironmentMembership.objects.create(user=self.teacher, environment=self.env2, role="owner")
        EnvironmentMembership.objects.create(user=self.other_teacher, environment=self.other_env, role="owner")

        login = self.client.post("/api/v1/auth/teacher/login/", {"identifier": "t1@example.com", "password": VALID_PW})
        auth(self.client, login)

    def test_lists_only_own_environments(self):
        r = self.client.get("/api/v1/environments/teacher/")
        self.assertEqual(r.status_code, 200)
        names = {e["name"] for e in r.data}
        self.assertEqual(names, {"الصف الثالث", "الصف الثاني"})

    def test_cannot_enter_another_teachers_environment(self):
        r = self.client.post(f"/api/v1/environments/teacher/{self.other_env.id}/enter/")
        self.assertEqual(r.status_code, 404)

    def test_enter_updates_last_accessed(self):
        r = self.client.post(f"/api/v1/environments/teacher/{self.env1.id}/enter/")
        self.assertEqual(r.status_code, 200)
        m = EnvironmentMembership.objects.get(user=self.teacher, environment=self.env1)
        self.assertIsNotNone(m.last_accessed_at)

    def test_student_cannot_access_teacher_endpoint(self):
        student = User.objects.create_user(role=User.Role.STUDENT, phone="201099999999", password=VALID_PW, is_active=True)
        login = self.client.post("/api/v1/auth/student/login/", {"phone": "201099999999", "password": VALID_PW})
        c2 = APIClient()
        c2.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
        r = c2.get("/api/v1/environments/teacher/")
        self.assertEqual(r.status_code, 403)


class AddStudentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="Ahmed", email="t3@example.com", phone="201030303030",
            password=VALID_PW, is_active=True,
        )
        self.env = Environment.objects.create(owner=self.teacher, name="Env")
        login = self.client.post("/api/v1/auth/teacher/login/", {"identifier": "t3@example.com", "password": VALID_PW})
        auth(self.client, login)

    def test_add_new_student(self):
        r = self.client.post("/api/v1/environments/students/", {
            "name": "طالب جديد", "phone": "201040404040", "environment_id": self.env.id,
        })
        self.assertEqual(r.status_code, 201, r.data)
        user = User.objects.get(phone="201040404040")
        self.assertEqual(user.role, "student")
        self.assertFalse(user.is_active)
        self.assertFalse(user.has_usable_password())

    def test_add_same_student_to_second_environment_reuses_user(self):
        env2 = Environment.objects.create(owner=self.teacher, name="Env2")
        self.client.post("/api/v1/environments/students/", {
            "name": "طالب", "phone": "201050505050", "environment_id": self.env.id,
        })
        r2 = self.client.post("/api/v1/environments/students/", {
            "name": "طالب", "phone": "201050505050", "environment_id": env2.id,
        })
        self.assertEqual(r2.status_code, 201)
        self.assertEqual(User.objects.filter(phone="201050505050").count(), 1)
        self.assertEqual(EnvironmentMembership.objects.filter(user__phone="201050505050").count(), 2)

    def test_cannot_add_student_to_someone_elses_environment(self):
        other_teacher = User.objects.create_user(
            role=User.Role.TEACHER, email="t4@example.com", phone="201060606060", password=VALID_PW, is_active=True,
        )
        other_env = Environment.objects.create(owner=other_teacher, name="Other")
        r = self.client.post("/api/v1/environments/students/", {
            "name": "X", "phone": "201070707070", "environment_id": other_env.id,
        })
        self.assertEqual(r.status_code, 400)

    def test_phone_already_used_by_non_student_role_rejected(self):
        User.objects.create_user(role=User.Role.TEACHER, email="dup2@example.com", phone="201080808080", password=VALID_PW)
        r = self.client.post("/api/v1/environments/students/", {
            "name": "X", "phone": "201080808080", "environment_id": self.env.id,
        })
        self.assertEqual(r.status_code, 400)


class StudentEnvironmentTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.teacher = User.objects.create_user(
            role=User.Role.TEACHER, name="أستاذ أحمد", email="t5@example.com", phone="201090909090",
            password=VALID_PW, is_active=True,
        )
        self.env = Environment.objects.create(owner=self.teacher, name="Env")
        self.student = User.objects.create_user(
            role=User.Role.STUDENT, name="Student", phone="201091919191", password=VALID_PW, is_active=True,
        )
        EnvironmentMembership.objects.create(user=self.student, environment=self.env, role="student")
        login = self.client.post("/api/v1/auth/student/login/", {"phone": "201091919191", "password": VALID_PW})
        auth(self.client, login)

    def test_lists_teacher_identity_not_environment_name(self):
        r = self.client.get("/api/v1/environments/student/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.data[0]["name"], "أستاذ أحمد")
        self.assertEqual(r.data[0]["initials"], "أ")
