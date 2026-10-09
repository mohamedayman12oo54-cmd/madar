"""Fast-Session attendance/recitation marking (docs: BR-2 per-tap persistence).

Rewritten from an obsolete suite that targeted a REST list/update API
(`/scheduling/attendance/` + `/attendance/<pk>/`) which no longer exists: the
documented design is per-tap marking (`attendance/mark/`, `recitation/mark/`)
plus a single roster read (`sessions/<pk>/roster/`). The cross-tenant and
validation intent of the original tests is preserved.
"""
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone

from academics.models import Enrollment, Grade, Group
from environments.tenancy_testing import TenantTestCase

from .models import AttendanceRecord, RecitationRecord, SessionInstance

MARK_ATTENDANCE_URL = "/api/v1/scheduling/attendance/mark/"
MARK_RECITATION_URL = "/api/v1/scheduling/recitation/mark/"


def roster_url(pk):
    return f"/api/v1/scheduling/sessions/{pk}/roster/"


class FastSessionMarkingTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.group1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.group2 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        self.session1 = SessionInstance.objects.create(environment=self.env_a, group=self.group1, scheduled_at=timezone.now())
        self.session2 = SessionInstance.objects.create(environment=self.env_a, group=self.group2, scheduled_at=timezone.now())
        # Capture is only allowed while a session is OPEN (session lifecycle).
        self.session1.open()
        self.session2.open()
        self.s1 = self.make_student_in(self.env_a, "201555100001", "طالب ١")
        self.s2 = self.make_student_in(self.env_a, "201555100002", "طالب ٢")
        self.s3 = self.make_student_in(self.env_a, "201555100003", "طالب ٣")
        # INV-4: group membership is an M2M set WITHIN the enrollment's grade.
        self.enr1 = Enrollment.objects.create(environment=self.env_a, student=self.s1, grade=self.grade)
        self.enr1.groups.set([self.group1])
        self.enr2 = Enrollment.objects.create(environment=self.env_a, student=self.s2, grade=self.grade)
        self.enr2.groups.set([self.group1])
        self.enr3 = Enrollment.objects.create(environment=self.env_a, student=self.s3, grade=self.grade)
        self.enr3.groups.set([self.group2])

    def mark(self, session, enrollment, status, url=MARK_ATTENDANCE_URL, client=None, env=None):
        return (client or self.client_a).put(
            url,
            {"session_id": session.id, "enrollment_id": enrollment.id, "status": status},
            format="json",
            **self.with_env((env or self.env_a).id),
        )

    # -- happy path ----------------------------------------------------
    def test_mark_present_persists_one_record(self):
        r = self.mark(self.session1, self.enr1, "present")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["status"], "present")
        record = AttendanceRecord.objects.get(session=self.session1, enrollment=self.enr1)
        self.assertEqual(record.status, "present")
        self.assertEqual(record.environment_id, self.env_a.id)

    def test_remark_corrects_in_place_and_does_not_duplicate(self):
        """Attendance is correctable (INV-8): a second tap updates, never
        creates a second row for the same (session, enrollment)."""
        self.mark(self.session1, self.enr1, "present")
        self.mark(self.session1, self.enr1, "absent")
        self.assertEqual(AttendanceRecord.objects.filter(session=self.session1, enrollment=self.enr1).count(), 1)
        self.assertEqual(AttendanceRecord.objects.get(session=self.session1, enrollment=self.enr1).status, "absent")

    def test_recitation_marks_independently_of_attendance(self):
        self.mark(self.session1, self.enr1, "present")
        r = self.mark(self.session1, self.enr1, "studied", url=MARK_RECITATION_URL)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(RecitationRecord.objects.get(session=self.session1, enrollment=self.enr1).status, "studied")
        self.assertEqual(AttendanceRecord.objects.get(session=self.session1, enrollment=self.enr1).status, "present")

    # -- validation ----------------------------------------------------
    def test_invalid_status_rejected(self):
        self.assertEqual(self.mark(self.session1, self.enr1, "late").status_code, 400)
        self.assertFalse(AttendanceRecord.objects.filter(session=self.session1).exists())

    def test_enrollment_outside_the_sessions_group_is_rejected(self):
        """enr3 is in group2; session1 belongs to group1."""
        r = self.mark(self.session1, self.enr3, "present")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertFalse(AttendanceRecord.objects.filter(session=self.session1, enrollment=self.enr3).exists())

    def test_model_level_clean_rejects_mismatched_group(self):
        record = AttendanceRecord(environment=self.env_a, session=self.session2, enrollment=self.enr1)
        with self.assertRaises(DjangoValidationError):
            record.full_clean()

    # -- tenant isolation ----------------------------------------------
    def test_teacher_b_cannot_mark_into_teacher_as_session(self):
        self.assert_cross_tenant_denied(
            "put",
            MARK_ATTENDANCE_URL,
            body={"session_id": self.session1.id, "enrollment_id": self.enr1.id, "status": "present"},
        )
        self.assertFalse(AttendanceRecord.objects.filter(session=self.session1).exists())

    def test_teacher_bs_own_context_cannot_reach_teacher_as_ids(self):
        """Even inside B's own environment, A's session id must not resolve."""
        r = self.mark(self.session1, self.enr1, "present", client=self.client_b, env=self.env_b)
        self.assertEqual(r.status_code, 404, r.content)
        self.assertFalse(AttendanceRecord.objects.filter(session=self.session1).exists())

    def test_roster_is_scoped_to_the_sessions_group(self):
        self.mark(self.session1, self.enr1, "present")
        r = self.client_a.get(roster_url(self.session1.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        ids = {s["enrollment_id"] for s in body["students"]}
        self.assertEqual(ids, {self.enr1.id, self.enr2.id})  # group1 only
        self.assertEqual(body["counts"]["present"], 1)
        self.assertEqual(body["counts"]["total"], 2)
        marked = next(s for s in body["students"] if s["enrollment_id"] == self.enr1.id)
        unmarked = next(s for s in body["students"] if s["enrollment_id"] == self.enr2.id)
        self.assertEqual(marked["attendance"], "present")
        self.assertIsNone(unmarked["attendance"])

    def test_cross_tenant_roster_read_is_denied(self):
        self.assert_cross_tenant_denied("get", roster_url(self.session1.id))

    def test_marking_requires_an_open_session(self):
        """Documented lifecycle: capture only while the session is Open."""
        closed = SessionInstance.objects.create(
            environment=self.env_a, group=self.group1, scheduled_at=timezone.now()
        )  # PLANNED, never opened
        r = self.mark(closed, self.enr1, "present")
        self.assertEqual(r.status_code, 400, r.content)
        self.assertFalse(AttendanceRecord.objects.filter(session=closed).exists())
