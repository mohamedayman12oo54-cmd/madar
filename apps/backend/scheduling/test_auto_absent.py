"""Closing a session records Absent for everyone nobody marked; sessions have
an end time and close themselves when it passes."""
import datetime as dt
from io import StringIO

from django.core.management import call_command
from django.utils import timezone

from accounts.testing import make_enrollment
from notifications.models import Notification

from .models import AttendanceRecord, Schedule, SessionInstance
from .services import close_due_sessions, generate_planned_sessions
from .tests import Base

H = dt.timedelta(hours=1)


def absences():
    return Notification.objects.filter(type=Notification.Type.ABSENT)


class AutoAbsentTests(Base):
    def setUp(self):
        super().setUp()
        now = timezone.now()
        self.session.scheduled_at = now - H
        self.session.ends_at = now + H
        self.session.save(update_fields=["scheduled_at", "ends_at"])

    def rec(self, enr):
        return AttendanceRecord.objects.filter(session=self.session, enrollment=enr).first()

    def time_passes(self, minutes_after_end=1):
        """Move the session's lesson into the past, the way waiting would."""
        now = timezone.now()
        SessionInstance.objects.filter(pk=self.session.pk).update(
            scheduled_at=now - 2 * H, ends_at=now - dt.timedelta(minutes=minutes_after_end),
            opened_at=now - 2 * H)
        self.session.refresh_from_db()

    # --- closing by the teacher -------------------------------------------------
    def test_closing_marks_everyone_unmarked_absent_and_keeps_existing_marks(self):
        self.open()
        self.assertEqual(self.mark("attendance", self.e1, "present").status_code, 200)
        r = self.call("post", f"sessions/{self.session.id}/close/")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(self.rec(self.e1).status, "present")
        self.assertFalse(self.rec(self.e1).auto_marked)
        absent = self.rec(self.e2)
        self.assertEqual((absent.status, absent.auto_marked), ("absent", True))

    def test_the_usual_absence_notification_fires_only_for_the_auto_absent(self):
        self.open()
        self.mark("attendance", self.e1, "present")
        self.call("post", f"sessions/{self.session.id}/close/")
        self.assertEqual(absences().count(), 1)
        self.assertEqual(absences().first().enrollment_id, self.e2.id)

    def test_inactive_students_and_other_groups_are_not_marked(self):
        other = make_enrollment(self.env_a, self.make_student_in(self.env_a, "201010100003", name="غيره"), self.grade, self.g2)
        gone = make_enrollment(self.env_a, self.make_student_in(self.env_a, "201010100004", name="موقوف"), self.grade, self.g1)
        gone.is_active = False
        gone.save(update_fields=["is_active"])
        self.open()
        self.call("post", f"sessions/{self.session.id}/close/")
        self.assertIsNone(self.rec(other))
        self.assertIsNone(self.rec(gone))

    def test_closing_twice_never_duplicates_anything(self):
        self.open()
        self.call("post", f"sessions/{self.session.id}/close/")
        self.assertEqual(self.call("post", f"sessions/{self.session.id}/close/").status_code, 400)
        self.assertEqual(AttendanceRecord.objects.filter(session=self.session).count(), 2)
        self.assertEqual(absences().count(), 2)

    # --- closing by the clock ---------------------------------------------------
    def test_a_session_past_its_end_time_closes_and_records_absences(self):
        self.open()
        self.mark("attendance", self.e1, "present")
        self.time_passes()
        self.assertEqual(close_due_sessions(), 1)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "closed")
        self.assertEqual(self.rec(self.e1).status, "present")
        self.assertEqual(self.rec(self.e2).status, "absent")

    def test_a_session_still_inside_its_window_stays_open(self):
        self.open()
        self.assertEqual(close_due_sessions(), 0)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "open")
        self.assertFalse(AttendanceRecord.objects.filter(session=self.session).exists())

    def test_without_an_end_time_nothing_closes_by_itself(self):
        SessionInstance.objects.filter(pk=self.session.pk).update(ends_at=None)
        self.open()
        SessionInstance.objects.filter(pk=self.session.pk).update(opened_at=timezone.now() - 48 * H)
        self.assertEqual(close_due_sessions(), 0)

    def test_the_clock_only_closes_sessions_of_the_given_environment(self):
        self.open()
        self.time_passes()
        self.assertEqual(close_due_sessions(self.env_b), 0)
        self.assertEqual(close_due_sessions(self.env_a), 1)

    def test_listing_sessions_closes_overdue_ones_without_the_cron(self):
        self.open()
        self.time_passes()
        r = self.call("get", "sessions/")
        self.assertEqual(r.status_code, 200)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "closed")
        self.assertEqual(self.rec(self.e2).status, "absent")

    def test_marking_after_the_end_time_is_refused_and_the_session_closes(self):
        self.open()
        self.time_passes()
        r = self.mark("attendance", self.e1, "present")
        self.assertEqual(r.status_code, 400, r.content)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "closed")
        self.assertEqual(self.rec(self.e1).status, "absent")  # nobody marked him in time

    def test_the_management_command_does_the_same(self):
        self.open()
        self.time_passes()
        out = StringIO()
        call_command("close_due_sessions", stdout=out)
        self.assertIn("Closed 1", out.getvalue())

    # --- reopening --------------------------------------------------------------
    def test_reopen_then_mark_overrides_the_automatic_absence(self):
        self.open()
        self.time_passes()
        close_due_sessions()
        self.assertEqual(self.call("post", f"sessions/{self.session.id}/reopen/").status_code, 200)
        # the end time is long gone, yet the reopened session must stay open
        self.assertEqual(close_due_sessions(), 0)
        self.assertEqual(self.mark("attendance", self.e2, "present").status_code, 200)
        fixed = self.rec(self.e2)
        self.assertEqual((fixed.status, fixed.auto_marked), ("present", False))

    def test_a_teacher_confirming_an_automatic_absence_takes_ownership(self):
        self.open()
        self.call("post", f"sessions/{self.session.id}/close/")
        self.call("post", f"sessions/{self.session.id}/reopen/")
        self.assertEqual(self.mark("attendance", self.e2, "absent").status_code, 200)
        self.assertFalse(self.rec(self.e2).auto_marked)
        self.assertEqual(absences().filter(enrollment=self.e2).count(), 1)  # no second notification

    def test_a_session_opened_after_its_end_time_gets_a_grace_period(self):
        now = timezone.now()
        SessionInstance.objects.filter(pk=self.session.pk).update(
            scheduled_at=now - 3 * H, ends_at=now - 2 * H)
        self.open()
        self.assertEqual(close_due_sessions(), 0)
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, "open")

    def test_the_roster_flags_automatic_absences(self):
        self.open()
        self.call("post", f"sessions/{self.session.id}/close/")
        body = self.call("get", f"sessions/{self.session.id}/roster/").json()
        self.assertEqual(body["counts"]["auto_absent"], 2)
        self.assertTrue(all(s["auto_absent"] for s in body["students"]))


class EndTimeInputTests(Base):
    def test_bulk_sessions_store_the_end_time(self):
        start = (timezone.now() + dt.timedelta(days=2)).replace(microsecond=0)
        r = self.call("post", "sessions/bulk/", {
            "grade_id": self.grade.id, "scheduled_at": start.isoformat(), "ends_at": (start + H).isoformat()})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(
            set(SessionInstance.objects.filter(scheduled_at=start).values_list("ends_at", flat=True)), {start + H})

    def test_an_end_before_the_start_is_refused(self):
        start = (timezone.now() + dt.timedelta(days=2)).replace(microsecond=0)
        r = self.call("post", "sessions/bulk/", {
            "grade_id": self.grade.id, "scheduled_at": start.isoformat(), "ends_at": (start - H).isoformat()})
        self.assertEqual(r.status_code, 400, r.content)
        self.assertFalse(SessionInstance.objects.filter(scheduled_at=start).exists())

    def test_a_schedule_needs_its_end_after_its_start(self):
        bad = self.call("post", "schedules/", {"group_id": self.g1.id, "weekday": 5, "start_time": "17:00", "end_time": "16:00"})
        self.assertEqual(bad.status_code, 400, bad.content)
        ok = self.call("post", "schedules/", {"group_id": self.g1.id, "weekday": 5, "start_time": "16:00", "end_time": "17:00"})
        self.assertEqual(ok.status_code, 201, ok.content)
        self.assertEqual(ok.json()["end_time"], "17:00:00")

    def test_generated_sessions_inherit_the_schedule_end_time(self):
        today = timezone.localdate()
        Schedule.objects.create(
            environment=self.env_a, group=self.g2, weekday=(today + dt.timedelta(days=1)).weekday(),
            start_time=dt.time(16, 0), end_time=dt.time(17, 0))
        made = generate_planned_sessions(self.env_a, 1, group=self.g2, today=today)
        self.assertEqual(len(made), 1)
        local = timezone.localtime
        self.assertEqual(local(made[0].ends_at).time(), dt.time(17, 0))
        self.assertEqual(made[0].ends_at - made[0].scheduled_at, H)
