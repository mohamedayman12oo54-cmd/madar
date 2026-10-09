"""Sessions, schedules, the Fast Session (attendance + recitation) and their
notification side-effects — checked against the documentation rules."""
import datetime as dt

from django.utils import timezone

from academics.models import Grade, Group
from accounts.testing import make_enrollment
from environments.tenancy_testing import TenantTestCase
from notifications.models import Notification

from .models import AttendanceRecord, RecitationRecord, Schedule, SessionInstance

S = "/api/v1/scheduling/"


class Base(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=100)
        self.g1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.g2 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        self.s1 = self.make_student_in(self.env_a, "201010100001", name="أحمد")
        self.s2 = self.make_student_in(self.env_a, "201010100002", name="سارة")
        self.e1 = make_enrollment(self.env_a, self.s1, self.grade, self.g1)
        self.e2 = make_enrollment(self.env_a, self.s2, self.grade, self.g1)
        self.session = SessionInstance.objects.create(environment=self.env_a, group=self.g1, scheduled_at=timezone.now())

    def call(self, method, path, body=None, client=None, env=None):
        c = client or self.client_a
        fn = getattr(c, method)
        kw = self.with_env((env or self.env_a).id)
        return fn(S + path, body, format="json", **kw) if body is not None else fn(S + path, **kw)

    def open(self):
        self.session.refresh_from_db()
        if self.session.status == "planned":
            self.assertEqual(self.call("post", f"sessions/{self.session.id}/open/").status_code, 200)

    def mark(self, kind, enrollment, status):
        return self.call("put", f"{kind}/mark/", {"session_id": self.session.id, "enrollment_id": enrollment.id, "status": status})


class SessionLifecycleTests(Base):
    def test_open_close_reopen_keeps_the_same_row(self):
        self.open()
        self.assertEqual(self.call("post", f"sessions/{self.session.id}/close/").status_code, 200)
        r = self.call("post", f"sessions/{self.session.id}/reopen/")
        self.assertEqual(r.json()["reopened_count"], 1)
        self.assertEqual(SessionInstance.objects.filter(group=self.g1).count(), 1)

    def test_illegal_transitions_are_rejected(self):
        self.assertEqual(self.call("post", f"sessions/{self.session.id}/close/").status_code, 400)
        self.assertEqual(self.call("post", f"sessions/{self.session.id}/reopen/").status_code, 400)
        self.open()
        self.assertEqual(self.call("post", f"sessions/{self.session.id}/open/").status_code, 400)

    def test_opening_a_session_notifies_nobody(self):
        """Docs: the notification catalog is bounded to five events."""
        self.open()
        self.assertEqual(Notification.objects.count(), 0)

    def test_cannot_use_another_teachers_session(self):
        self.assert_cross_tenant_denied("post", f"{S}sessions/{self.session.id}/open/")
        self.assert_cross_tenant_denied("get", f"{S}sessions/{self.session.id}/roster/")


class FastSessionTests(Base):
    def test_nothing_is_prefilled_roster_shows_unmarked(self):
        self.open()
        self.assertEqual(AttendanceRecord.objects.count(), 0)
        body = self.call("get", f"sessions/{self.session.id}/roster/").json()
        self.assertEqual([s["name"] for s in body["students"]], ["أحمد", "سارة"])
        self.assertTrue(all(s["attendance"] is None and s["recitation"] is None for s in body["students"]))

    def test_cannot_mark_before_open_or_after_close(self):
        self.assertEqual(self.mark("attendance", self.e1, "present").status_code, 400)
        self.open()
        self.assertEqual(self.mark("attendance", self.e1, "present").status_code, 200)
        self.call("post", f"sessions/{self.session.id}/close/")
        self.assertEqual(self.mark("attendance", self.e1, "absent").status_code, 400)

    def test_absent_fires_one_notification_to_that_student_and_retap_does_not_duplicate(self):
        self.open()
        for _ in range(3):
            self.assertEqual(self.mark("attendance", self.e1, "absent").status_code, 200)
        n = Notification.objects.get()
        self.assertEqual((n.type, n.recipient_id, n.enrollment_id), ("absent", self.s1.id, self.e1.id))
        self.assertEqual(n.delivery_status, "pending")

    def test_present_fires_nothing_and_correction_to_absent_fires_a_new_one(self):
        self.open()
        self.mark("attendance", self.e1, "present")
        self.assertEqual(Notification.objects.count(), 0)
        self.mark("attendance", self.e1, "absent")
        self.assertEqual(Notification.objects.filter(type="absent").count(), 1)

    def test_correcting_absent_to_present_does_not_retract_the_sent_notification(self):
        self.open()
        self.mark("attendance", self.e1, "absent")
        self.mark("attendance", self.e1, "present")
        self.assertEqual(Notification.objects.filter(type="absent").count(), 1)
        self.assertEqual(AttendanceRecord.objects.get(enrollment=self.e1).status, "present")

    def test_recitation_not_studied_notifies_studied_does_not(self):
        self.open()
        self.mark("recitation", self.e1, "studied")
        self.mark("recitation", self.e2, "not_studied")
        self.assertEqual(list(Notification.objects.values_list("type", "enrollment_id")), [("not_studied", self.e2.id)])
        self.assertEqual(RecitationRecord.objects.count(), 2)

    def test_invalid_status_rejected(self):
        self.open()
        self.assertEqual(self.mark("attendance", self.e1, "late").status_code, 400)
        self.assertEqual(self.mark("recitation", self.e1, "skip").status_code, 400)  # skip records nothing

    def test_student_outside_the_session_group_cannot_be_marked(self):
        other = make_enrollment(self.env_a, self.make_student_in(self.env_a, "201010100003"), self.grade, self.g2)
        self.open()
        self.assertEqual(self.mark("attendance", other, "present").status_code, 400)

    def test_student_in_two_groups_of_their_grade_is_marked_independently(self):
        self.e1.groups.add(self.g2)
        s2 = SessionInstance.objects.create(environment=self.env_a, group=self.g2, scheduled_at=timezone.now())
        self.open()
        self.mark("attendance", self.e1, "present")
        self.call("post", f"sessions/{s2.id}/open/")
        r = self.call("put", "attendance/mark/", {"session_id": s2.id, "enrollment_id": self.e1.id, "status": "absent"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(AttendanceRecord.objects.filter(enrollment=self.e1).count(), 2)

    def test_inactive_student_cannot_be_marked_and_is_not_on_the_roster(self):
        self.e2.is_active = False
        self.e2.save()
        self.open()
        self.assertEqual(self.mark("attendance", self.e2, "present").status_code, 400)
        names = [s["name"] for s in self.call("get", f"sessions/{self.session.id}/roster/").json()["students"]]
        self.assertEqual(names, ["أحمد"])

    def test_cannot_mark_another_teachers_enrollment_or_session(self):
        self.open()
        c = self.client_b
        r = c.put(S + "attendance/mark/", {"session_id": self.session.id, "enrollment_id": self.e1.id, "status": "present"},
                  format="json", **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(AttendanceRecord.objects.count(), 0)


class ScheduleTests(Base):
    def test_create_list_and_reject_duplicate_slot(self):
        body = {"group_id": self.g1.id, "weekday": 0, "start_time": "18:00"}
        self.assertEqual(self.call("post", "schedules/", body).status_code, 201)
        self.assertEqual(self.call("post", "schedules/", body).status_code, 400)
        self.assertEqual(self.call("get", "schedules/").json()["count"], 1)

    def test_cannot_schedule_in_another_teachers_group(self):
        other = Group.objects.create(environment=self.env_b, grade=Grade.objects.create(environment=self.env_b, name="x"), name="B")
        r = self.call("post", "schedules/", {"group_id": other.id, "weekday": 1, "start_time": "10:00"})
        self.assertEqual(r.status_code, 400)

    def test_generate_is_idempotent_and_only_future(self):
        today = timezone.localdate()
        Schedule.objects.create(environment=self.env_a, group=self.g1, weekday=(today.weekday() + 1) % 7, start_time=dt.time(18, 0))
        r1 = self.call("post", "sessions/generate/", {"weeks": 2})
        self.assertEqual(r1.status_code, 201)
        created = r1.json()["created"]
        self.assertIn(created, (2,))
        self.assertEqual(self.call("post", "sessions/generate/", {"weeks": 2}).json()["created"], 0)
        self.assertTrue(SessionInstance.objects.filter(group=self.g1, status="planned").count() >= created)

    def test_generate_weeks_is_capped(self):
        self.assertEqual(self.call("post", "sessions/generate/", {"weeks": 52}).status_code, 400)
