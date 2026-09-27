from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from academics.models import Enrollment, Grade, Group
from environments.tenancy_testing import TenantTestCase

from .models import AttendanceRecord, SessionInstance

ATTENDANCE_URL = "/api/v1/scheduling/attendance/"


def attendance_url(pk):
    return f"{ATTENDANCE_URL}{pk}/"


class AttendanceListAndUpdateTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.group1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.group2 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        self.session1 = SessionInstance.objects.create(environment=self.env_a, group=self.group1, scheduled_at=timezone.now())
        self.session2 = SessionInstance.objects.create(environment=self.env_a, group=self.group2, scheduled_at=timezone.now())

        self.s1 = self.make_student_in(self.env_a, "201120000001", name="أحمد")
        self.s2 = self.make_student_in(self.env_a, "201120000002", name="سارة")
        self.s3 = self.make_student_in(self.env_a, "201120000003", name="منى")
        self.enr1 = Enrollment.objects.create(environment=self.env_a, student=self.s1, grade=self.grade, group=self.group1)
        self.enr2 = Enrollment.objects.create(environment=self.env_a, student=self.s2, grade=self.grade, group=self.group1)
        self.enr3 = Enrollment.objects.create(environment=self.env_a, student=self.s3, grade=self.grade, group=self.group2)

        self.session1.open()
        self.session2.open()

    def _items(self, r):
        return r.json()["results"]

    def test_list_filtered_by_session(self):
        r = self.client_a.get(f"{ATTENDANCE_URL}?session_id={self.session1.id}", **self.with_env(self.env_a.id))
        names = {a["student"]["name"] for a in self._items(r)}
        self.assertEqual(names, {"أحمد", "سارة"})

    def test_list_filtered_by_group(self):
        r = self.client_a.get(f"{ATTENDANCE_URL}?group_id={self.group2.id}", **self.with_env(self.env_a.id))
        names = {a["student"]["name"] for a in self._items(r)}
        self.assertEqual(names, {"منى"})

    def test_list_filtered_by_enrollment_gives_history_across_sessions(self):
        session1b = SessionInstance.objects.create(environment=self.env_a, group=self.group1, scheduled_at=timezone.now())
        session1b.open()
        r = self.client_a.get(f"{ATTENDANCE_URL}?enrollment_id={self.enr1.id}", **self.with_env(self.env_a.id))
        self.assertEqual(len(self._items(r)), 2)  # session1 and session1b

    def test_mark_present(self):
        record = AttendanceRecord.objects.get(session=self.session1, enrollment=self.enr1)
        r = self.client_a.patch(attendance_url(record.id), {"status": "present"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "present")
        record.refresh_from_db()
        self.assertEqual(record.status, "present")

    def test_cannot_change_session_or_enrollment_via_update(self):
        record = AttendanceRecord.objects.get(session=self.session1, enrollment=self.enr1)
        r = self.client_a.patch(
            attendance_url(record.id), {"status": "present", "session": self.session2.id, "enrollment": self.enr3.id},
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 200)
        record.refresh_from_db()
        self.assertEqual(record.session_id, self.session1.id)
        self.assertEqual(record.enrollment_id, self.enr1.id)

    def test_invalid_status_rejected(self):
        record = AttendanceRecord.objects.get(session=self.session1, enrollment=self.enr1)
        r = self.client_a.patch(attendance_url(record.id), {"status": "late"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_cannot_read_or_update_another_teachers_attendance_record(self):
        record = AttendanceRecord.objects.get(session=self.session1, enrollment=self.enr1)
        self.assert_cross_tenant_denied("get", attendance_url(record.id))
        self.assert_cross_tenant_denied("patch", attendance_url(record.id), body={"status": "present"})

    def test_cross_tenant_session_id_filter_returns_nothing_not_someone_elses_data(self):
        """Teacher B has no session with Teacher A's session id, so the
        cross-tenant queryset filter yields an empty (not error, not leaked) list."""
        r = self.client_b.get(f"{ATTENDANCE_URL}?session_id={self.session1.id}", **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(self._items(r), [])

    def test_model_level_clean_rejects_mismatched_group(self):
        other_session = SessionInstance(environment=self.env_a, group=self.group2, scheduled_at=timezone.now())
        other_session.save()
        record = AttendanceRecord(environment=self.env_a, session=other_session, enrollment=self.enr1)  # enr1 is in group1
        with self.assertRaises(DjangoValidationError):
            record.clean()
