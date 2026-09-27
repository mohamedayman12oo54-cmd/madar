"""
Phase 3 — SessionInstance lifecycle (planned -> open -> closed -> reopen ->
open -> closed), and cross-tenant isolation via the same TenantTestCase
harness Phase 1/2 used.
"""
from django.utils import timezone

from academics.models import Enrollment, Grade, Group
from environments.tenancy_testing import TenantTestCase

from .models import AttendanceRecord, SessionInstance

SESSIONS_URL = "/api/v1/scheduling/sessions/"


def session_url(pk):
    return f"{SESSIONS_URL}{pk}/"


def open_url(pk):
    return f"{SESSIONS_URL}{pk}/open/"


def close_url(pk):
    return f"{SESSIONS_URL}{pk}/close/"


def reopen_url(pk):
    return f"{SESSIONS_URL}{pk}/reopen/"


class SessionCreateAndListTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade_a = Grade.objects.create(environment=self.env_a, name="أول")
        self.group_a = Group.objects.create(environment=self.env_a, grade=self.grade_a, name="G1")
        self.grade_b = Grade.objects.create(environment=self.env_b, name="أول")
        self.group_b = Group.objects.create(environment=self.env_b, grade=self.grade_b, name="G1")

    def test_plan_a_session(self):
        r = self.client_a.post(
            SESSIONS_URL, {"group_id": self.group_a.id, "scheduled_at": "2026-10-01T18:00:00Z"},
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertEqual(body["status"], "planned")
        self.assertEqual(body["group"]["id"], self.group_a.id)
        self.assertIsNone(body["opened_at"])

    def test_cannot_plan_a_session_under_another_environments_group(self):
        r = self.client_a.post(
            SESSIONS_URL, {"group_id": self.group_b.id, "scheduled_at": "2026-10-01T18:00:00Z"},
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 400)
        self.assertFalse(SessionInstance.objects.filter(group=self.group_b).exists())

    def test_list_scoped_to_active_environment_and_filterable_by_group_and_status(self):
        s1 = SessionInstance.objects.create(environment=self.env_a, group=self.group_a, scheduled_at=timezone.now())
        SessionInstance.objects.create(environment=self.env_b, group=self.group_b, scheduled_at=timezone.now())
        group_a2 = Group.objects.create(environment=self.env_a, grade=self.grade_a, name="G2")
        SessionInstance.objects.create(environment=self.env_a, group=group_a2, scheduled_at=timezone.now())

        r = self.client_a.get(SESSIONS_URL, **self.with_env(self.env_a.id))
        self.assertEqual(len(r.json()["results"]), 2)

        r2 = self.client_a.get(f"{SESSIONS_URL}?group_id={self.group_a.id}", **self.with_env(self.env_a.id))
        ids = [s["id"] for s in r2.json()["results"]]
        self.assertEqual(ids, [s1.id])

    def test_cannot_read_another_teachers_session(self):
        s = SessionInstance.objects.create(environment=self.env_a, group=self.group_a, scheduled_at=timezone.now())
        self.assert_cross_tenant_denied("get", session_url(s.id))

    def test_cannot_open_another_teachers_session(self):
        s = SessionInstance.objects.create(environment=self.env_a, group=self.group_a, scheduled_at=timezone.now())
        self.assert_cross_tenant_denied("post", open_url(s.id))
        s.refresh_from_db()
        self.assertEqual(s.status, "planned")


class SessionLifecycleTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.group = Group.objects.create(environment=self.env_a, grade=grade, name="G1")
        self.session = SessionInstance.objects.create(environment=self.env_a, group=self.group, scheduled_at=timezone.now())
        self.student1 = self.make_student_in(self.env_a, "201110000001", name="أحمد")
        self.student2 = self.make_student_in(self.env_a, "201110000002", name="سارة")
        self.enr1 = Enrollment.objects.create(environment=self.env_a, student=self.student1, grade=grade, group=self.group)
        self.enr2 = Enrollment.objects.create(environment=self.env_a, student=self.student2, grade=grade, group=self.group)

    def test_full_lifecycle_planned_open_closed_reopened_closed(self):
        r = self.client_a.post(open_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "open")

        r = self.client_a.post(close_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "closed")

        r = self.client_a.post(reopen_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "open")
        self.assertEqual(r.json()["reopened_count"], 1)

        r = self.client_a.post(close_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["status"], "closed")
        self.assertEqual(r.json()["reopened_count"], 1)  # never resets

    def test_reopen_never_creates_a_new_session_row(self):
        self.session.open(); self.session.close()
        before = SessionInstance.objects.count()
        self.client_a.post(reopen_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(SessionInstance.objects.count(), before)
        self.session.refresh_from_db()
        self.assertEqual(self.session.reopened_count, 1)

    def test_cannot_open_an_already_open_session(self):
        self.session.open()
        r = self.client_a.post(open_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_cannot_close_a_planned_session(self):
        r = self.client_a.post(close_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_cannot_reopen_a_planned_or_open_session(self):
        r = self.client_a.post(reopen_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)
        self.session.open()
        r2 = self.client_a.post(reopen_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(r2.status_code, 400)

    def test_opening_generates_attendance_for_every_active_enrollment_defaulting_absent(self):
        self.client_a.post(open_url(self.session.id), **self.with_env(self.env_a.id))
        records = AttendanceRecord.objects.filter(session=self.session)
        self.assertEqual(records.count(), 2)
        self.assertTrue(all(r.status == "absent" for r in records))

    def test_inactive_enrollment_is_not_included_in_generated_roster(self):
        self.enr2.is_active = False
        self.enr2.save(update_fields=["is_active"])
        self.client_a.post(open_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(AttendanceRecord.objects.filter(session=self.session).count(), 1)
        self.assertTrue(AttendanceRecord.objects.filter(session=self.session, enrollment=self.enr1).exists())

    def test_marking_present_survives_a_close_and_reopen(self):
        self.session.open()
        record = AttendanceRecord.objects.get(session=self.session, enrollment=self.enr1)
        record.status = "present"
        record.save(update_fields=["status"])
        self.session.close()
        self.client_a.post(reopen_url(self.session.id), **self.with_env(self.env_a.id))
        record.refresh_from_db()
        self.assertEqual(record.status, "present")
        self.assertEqual(AttendanceRecord.objects.filter(session=self.session).count(), 2)

    def test_reopen_tops_up_roster_with_newly_enrolled_students(self):
        self.session.open(); self.session.close()
        grade = self.group.grade
        new_student = self.make_student_in(self.env_a, "201110000003", name="جديد")
        Enrollment.objects.create(environment=self.env_a, student=new_student, grade=grade, group=self.group)
        self.client_a.post(reopen_url(self.session.id), **self.with_env(self.env_a.id))
        self.assertEqual(AttendanceRecord.objects.filter(session=self.session).count(), 3)

    def test_reschedule_allowed_only_while_planned(self):
        r = self.client_a.patch(session_url(self.session.id), {"scheduled_at": "2027-01-01T10:00:00Z"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.session.open()
        r2 = self.client_a.patch(session_url(self.session.id), {"scheduled_at": "2027-02-02T10:00:00Z"}, **self.with_env(self.env_a.id))
        self.assertEqual(r2.status_code, 400)

    def test_cannot_reschedule_or_transition_another_teachers_session(self):
        self.assert_cross_tenant_denied("patch", session_url(self.session.id), body={"scheduled_at": "2027-01-01T10:00:00Z"})
        self.assert_cross_tenant_denied("post", close_url(self.session.id))
        self.assert_cross_tenant_denied("post", reopen_url(self.session.id))
