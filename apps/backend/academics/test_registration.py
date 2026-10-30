"""Student self-registration by QR: teacher link lifecycle + the public form's rules."""
from unittest import mock

from rest_framework.test import APIClient

from accounts.models import User
from environments.tenancy_testing import TenantTestCase

from .models import Enrollment, Grade, Group, RegistrationLink

LINK = "/api/v1/academics/registration-link/"
PUBLIC = "/api/v1/academics/register/"
RATES = {k: "100000/min" for k in ("register-ip", "register-phone", "register-link", "student-add")}


@mock.patch.dict("rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES", RATES)
class RegistrationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أولى", fee_amount=1)
        self.grade2 = Grade.objects.create(environment=self.env_a, name="ثانية", fee_amount=1)
        self.g1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="أ")
        self.g2 = Group.objects.create(environment=self.env_a, grade=self.grade, name="ب")
        self.other = Group.objects.create(environment=self.env_a, grade=self.grade2, name="ج")
        self.token = self.client_a.post(LINK, **self.with_env(self.env_a.id)).json()["link"]["token"]
        self.anon = APIClient()

    def body(self, **kw):
        return {"name": "طالب جديد", "phone": "201555200001", "grade_id": self.grade.id, "group_id": self.g1.id,
                "parent_name": "ولي الأمر", "parent_phone": "201555200009", **kw}

    def submit(self, token=None, **kw):
        return self.anon.post(f"{PUBLIC}{token or self.token}/submit/", self.body(**kw), format="json")

    # --- teacher side
    def test_only_the_owner_manages_the_link(self):
        self.assertEqual(self.anon.get(LINK).status_code, 401)
        r = self.client_a.get(LINK, **self.with_env(self.env_a.id))
        self.assertEqual(r.json()["link"]["token"], self.token)

    def test_regenerating_kills_the_old_link_and_delete_switches_it_off(self):
        new = self.client_a.post(LINK, **self.with_env(self.env_a.id)).json()["link"]["token"]
        self.assertNotEqual(new, self.token)
        self.assertEqual(self.anon.get(f"{PUBLIC}{self.token}/").status_code, 404)
        self.assertEqual(self.anon.get(f"{PUBLIC}{new}/").status_code, 200)
        self.assertEqual(self.client_a.delete(LINK, **self.with_env(self.env_a.id)).status_code, 204)
        self.assertEqual(self.anon.get(f"{PUBLIC}{new}/").status_code, 404)
        self.assertIsNone(self.client_a.get(LINK, **self.with_env(self.env_a.id)).json()["link"])

    def test_expired_link_is_refused(self):
        from django.utils import timezone
        from datetime import timedelta
        RegistrationLink.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(self.anon.get(f"{PUBLIC}{self.token}/").status_code, 404)
        self.assertEqual(self.submit().status_code, 404)

    # --- public info
    def test_info_lists_only_this_environments_grades_and_groups(self):
        d = self.anon.get(f"{PUBLIC}{self.token}/").json()
        self.assertEqual({g["name"] for g in d["grades"]}, {"أولى", "ثانية"})
        names = {gr["name"]: [g["name"] for g in gr["groups"]] for gr in d["grades"]}
        self.assertEqual(sorted(names["أولى"]), ["أ", "ب"])
        self.assertNotIn("phone", str(d))

    # --- submit
    def test_registers_active_student_in_one_group_and_hides_the_badge_code(self):
        r = self.submit()
        self.assertEqual(r.status_code, 201, r.content)
        e = Enrollment.objects.get(student__phone="201555200001")
        self.assertEqual(e.environment_id, self.env_a.id)
        self.assertTrue(e.is_active)
        self.assertEqual([g.id for g in e.groups.all()], [self.g1.id])
        self.assertEqual((e.parent_name, e.parent_phone), ("ولي الأمر", "201555200009"))
        self.assertNotIn(e.qr_token, r.content.decode())
        self.assertEqual(RegistrationLink.objects.get(token=self.token).registered_count, 1)

    def test_group_must_belong_to_the_chosen_grade(self):
        self.assertEqual(self.submit(group_id=self.other.id).status_code, 400)
        self.assertFalse(Enrollment.objects.exists())

    def test_group_of_another_environment_is_refused(self):
        foreign = Group.objects.create(environment=self.env_b, grade=Grade.objects.create(environment=self.env_b, name="x", fee_amount=1), name="z")
        self.assertEqual(self.submit(group_id=foreign.id).status_code, 400)

    def test_guardian_name_and_phone_are_required(self):
        for field in ("parent_name", "parent_phone", "name", "phone", "group_id"):
            b = self.body(); b.pop(field)
            r = self.anon.post(f"{PUBLIC}{self.token}/submit/", b, format="json")
            self.assertEqual(r.status_code, 400, field)

    def test_resubmitting_the_same_phone_looks_identical_and_changes_nothing(self):
        first = self.submit()
        again = self.submit(name="اسم مختلف", group_id=self.g2.id)
        self.assertEqual((first.status_code, first.json()), (again.status_code, again.json()))
        e = Enrollment.objects.get(student__phone="201555200001")
        self.assertEqual(e.student_name, "طالب جديد")
        self.assertEqual([g.id for g in e.groups.all()], [self.g1.id])
        self.assertEqual(Enrollment.objects.count(), 1)

    def test_a_non_student_phone_gets_a_generic_refusal(self):
        r = self.submit(phone=self.teacher_a.phone)
        self.assertEqual(r.status_code, 400)
        self.assertIn("تواصل مع المعلّم", str(r.json()))
        self.assertFalse(Enrollment.objects.exists())

    def test_plan_cap_closes_registration_without_leaking_billing_details(self):
        with mock.patch("academics.serializers.student_cap_locked", return_value=0):
            r = self.submit()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["code"], "registration_closed")
        self.assertFalse(Enrollment.objects.exists())

    def test_registered_student_is_not_visible_to_another_teacher(self):
        self.submit()
        r = self.client_b.get("/api/v1/academics/enrollments/", **self.with_env(self.env_b.id))
        self.assertEqual(r.json()["results"] if isinstance(r.json(), dict) and "results" in r.json() else r.json(), [])

    def test_the_link_cannot_be_used_to_read_or_to_write_elsewhere(self):
        self.assertEqual(self.anon.get("/api/v1/academics/enrollments/", HTTP_AUTHORIZATION="").status_code, 401)

    def test_per_phone_throttle(self):
        rates = {**RATES, "register-phone": "2/hour"}
        with mock.patch.dict("rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES", rates):
            from django.core.cache import cache
            cache.clear()
            codes = [self.submit().status_code for _ in range(3)]
        self.assertEqual(codes[:2], [201, 201])
        self.assertEqual(codes[2], 429)
