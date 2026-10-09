from decimal import Decimal

from academics.models import Grade, Group
from accounts.models import User
from accounts.testing import make_enrollment
from config.months import current_month
from environments.tenancy_testing import PASSWORD, TenantTestCase
from financials.models import MonthlyPayment

from rest_framework.test import APIClient


class OverviewTests(TenantTestCase):
    def test_overview_numbers_are_computed_for_the_callers_environment_only(self):
        ga = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=Decimal("100"))
        Group.objects.create(environment=self.env_a, grade=ga, name="G")
        s1 = self.make_student_in(self.env_a, "201016600001")
        s2 = self.make_student_in(self.env_a, "201016600002")
        e1 = make_enrollment(self.env_a, s1, ga)
        make_enrollment(self.env_a, s2, ga, is_active=False)
        MonthlyPayment.objects.create(environment=self.env_a, enrollment=e1, month=current_month(), status="paid", amount=Decimal("100"))
        gb = Grade.objects.create(environment=self.env_b, name="ب", fee_amount=Decimal("999"))
        make_enrollment(self.env_b, self.make_student_in(self.env_b, "201016600003"), gb)

        body = self.client_a.get("/api/v1/environments/overview/", **self.with_env(self.env_a.id)).json()
        self.assertEqual(body["students"], {"active": 1, "inactive": 1})
        self.assertEqual(body["structure"], {"grades": 1, "groups": 1})
        self.assertEqual((body["payments"]["expected_total"], body["payments"]["collected_total"], body["payments"]["outstanding_total"]),
                         ("100.00", "100.00", "0.00"))

    def test_overview_is_owner_only_and_tenant_isolated(self):
        self.assert_cross_tenant_denied("get", "/api/v1/environments/overview/")
        student = User.objects.create_user(role="student", name="s", phone="201016600009", password=PASSWORD, is_active=True)
        from accounts.testing import ensure_active_enrollment

        ensure_active_enrollment(student, env=self.env_a)
        c = APIClient()
        c.credentials(HTTP_AUTHORIZATION="Bearer " + c.post("/api/v1/auth/student/login/", {"phone": student.phone, "password": PASSWORD}).data["access"])
        self.assertEqual(c.get("/api/v1/environments/overview/", **self.with_env(self.env_a.id)).status_code, 403)


class SettingsTests(TenantTestCase):
    def test_rename_environment_only_name_and_stage(self):
        r = self.client_a.patch("/api/v1/environments/current/", {"name": "اسم جديد", "subject_stage": "ثانوي"}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.env_a.refresh_from_db()
        self.assertEqual((self.env_a.name, self.env_a.initials), ("اسم جديد", "ا"))
        bad = self.client_a.patch("/api/v1/environments/current/", {"owner": self.teacher_b.id}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(bad.status_code, 400)
        self.assert_cross_tenant_denied("patch", "/api/v1/environments/current/", body={"name": "x"})

    def test_edit_own_name_only(self):
        r = self.client_a.patch("/api/v1/auth/me/", {"name": "الأستاذ أحمد"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.teacher_a.refresh_from_db()
        self.assertEqual(self.teacher_a.name, "الأستاذ أحمد")
        for body in ({"email": "x@y.com"}, {"phone": "201000000000"}, {"role": "team"}, {"is_staff": True}):
            self.assertEqual(self.client_a.patch("/api/v1/auth/me/", body, format="json").status_code, 400, body)

    def test_change_password_requires_current_and_revokes_other_sessions(self):
        other = APIClient()
        other.credentials(HTTP_AUTHORIZATION="Bearer " + other.post("/api/v1/auth/teacher/login/", {"identifier": "a@example.com", "password": PASSWORD}).data["access"])
        new = "NewStr0ng!Pass1"
        bad = self.client_a.post("/api/v1/auth/change-password/", {"current_password": "wrong", "password": new, "password2": new}, format="json")
        self.assertEqual(bad.status_code, 400)
        weak = self.client_a.post("/api/v1/auth/change-password/", {"current_password": PASSWORD, "password": "123", "password2": "123"}, format="json")
        self.assertEqual(weak.status_code, 400)
        same = self.client_a.post("/api/v1/auth/change-password/", {"current_password": PASSWORD, "password": PASSWORD, "password2": PASSWORD}, format="json")
        self.assertEqual(same.status_code, 400)
        ok = self.client_a.post("/api/v1/auth/change-password/", {"current_password": PASSWORD, "password": new, "password2": new}, format="json")
        self.assertEqual(ok.status_code, 200, ok.content)
        self.assertEqual(other.get("/api/v1/auth/me/").status_code, 401)            # other device logged out
        fresh = APIClient()
        fresh.credentials(HTTP_AUTHORIZATION="Bearer " + ok.data["access"])
        self.assertEqual(fresh.get("/api/v1/auth/me/").status_code, 200)             # this device continues
        self.assertEqual(APIClient().post("/api/v1/auth/teacher/login/", {"identifier": "a@example.com", "password": PASSWORD}).status_code, 400)

    def test_sign_out_everywhere(self):
        self.assertEqual(self.client_a.post("/api/v1/auth/sign-out-everywhere/").status_code, 205)
        self.assertEqual(self.client_a.get("/api/v1/auth/me/").status_code, 401)
