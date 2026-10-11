"""A student of another group visits this session as a guest: his marks are
carried into HIS OWN group's session when it opens (never double counted).
Also: deleting a session planned by mistake - but never one holding marks."""
import datetime as dt

from django.utils import timezone

from accounts.testing import make_enrollment
from notifications.models import Notification

from .models import AttendanceRecord, GuestVisit, RecitationRecord, SessionInstance
from .tests import Base

NOW = timezone.now()


class GuestBase(Base):
    def setUp(self):
        super().setUp()
        # self.session = G1's session today (the HOST). The visitor belongs to G2.
        self.s3 = self.make_student_in(self.env_a, "201010100003", name="ضيف")
        self.e3 = make_enrollment(self.env_a, self.s3, self.grade, self.g2)
        self.home = SessionInstance.objects.create(
            environment=self.env_a, group=self.g2, scheduled_at=NOW + dt.timedelta(days=5))
        self.open()

    def guest(self, **body):
        return self.call("put", f"sessions/{self.session.id}/guests/{self.e3.id}/", body)

    def add(self, **extra):
        return self.call("post", f"sessions/{self.session.id}/guests/", {"enrollment_id": self.e3.id, **extra})

    def open_home(self):
        r = self.call("post", f"sessions/{self.home.id}/open/")
        self.assertEqual(r.status_code, 200, r.content)


class GuestVisitTests(GuestBase):
    def test_marks_are_kept_as_a_visit_not_as_records_on_the_host_session(self):
        r = self.guest(attendance="present", recitation="studied")
        self.assertEqual(r.status_code, 404)  # visit must be added first (or via scanner)
        self.assertEqual(self.add().status_code, 201)
        r = self.guest(attendance="present", recitation="studied")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["home_session"]["id"], self.home.id)  # defaulted to his next G2 session
        self.assertFalse(AttendanceRecord.objects.filter(session=self.session).exists())
        self.assertFalse(RecitationRecord.objects.filter(session=self.session).exists())

    def test_opening_his_own_session_records_everything_automatically(self):
        self.add(); self.guest(attendance="present", recitation="studied")
        self.open_home()
        a = AttendanceRecord.objects.get(session=self.home, enrollment=self.e3)
        self.assertEqual(a.status, "present")
        self.assertEqual(RecitationRecord.objects.get(session=self.home, enrollment=self.e3).status, "studied")
        # counted ONCE overall
        self.assertEqual(AttendanceRecord.objects.filter(enrollment=self.e3).count(), 1)
        roster = self.call("get", f"sessions/{self.home.id}/roster/").data
        row = next(s for s in roster["students"] if s["enrollment_id"] == self.e3.id)
        self.assertEqual(row["attendance"], "present")
        self.assertEqual(row["carried_from"]["session_id"], self.session.id)

    def test_absence_notification_fires_when_carried_not_before(self):
        self.add(); self.guest(attendance="absent")
        self.assertFalse(Notification.objects.filter(enrollment=self.e3, type="absent").exists())
        self.open_home()
        self.assertTrue(Notification.objects.filter(enrollment=self.e3, type="absent").exists())

    def test_without_a_target_it_lands_in_the_next_session_that_opens_for_his_group(self):
        self.home.delete()
        self.add(); self.guest(attendance="present")
        self.assertIsNone(GuestVisit.objects.get().home_session)
        later = SessionInstance.objects.create(environment=self.env_a, group=self.g2, scheduled_at=NOW + dt.timedelta(days=3))
        self.call("post", f"sessions/{later.id}/open/")
        self.assertEqual(AttendanceRecord.objects.get(session=later, enrollment=self.e3).status, "present")

    def test_a_stale_visit_is_not_dragged_into_a_session_months_later(self):
        self.home.delete()
        self.add(); self.guest(attendance="present")
        far = SessionInstance.objects.create(environment=self.env_a, group=self.g2, scheduled_at=NOW + dt.timedelta(days=60))
        self.call("post", f"sessions/{far.id}/open/")
        self.assertFalse(AttendanceRecord.objects.filter(session=far).exists())

    def test_what_the_teacher_already_marked_in_his_own_session_is_not_overwritten(self):
        self.add(); self.guest(attendance="present")
        self.home.refresh_from_db()
        self.home.status = "open"; self.home.save()          # opened elsewhere, mark made by hand
        AttendanceRecord.objects.create(environment=self.env_a, session=self.home, enrollment=self.e3, status="absent")
        self.home.status = "planned"; self.home.save()
        self.open_home()
        self.assertEqual(AttendanceRecord.objects.get(session=self.home, enrollment=self.e3).status, "absent")

    def test_if_his_session_is_already_open_the_mark_is_carried_at_once(self):
        self.open_home()
        self.add(); self.guest(attendance="present")
        self.assertEqual(AttendanceRecord.objects.get(session=self.home, enrollment=self.e3).status, "present")
        self.guest(attendance="absent")                      # correction follows
        self.assertEqual(AttendanceRecord.objects.get(session=self.home, enrollment=self.e3).status, "absent")

    def test_a_member_cannot_be_a_guest_and_a_closed_host_takes_no_guests(self):
        self.assertEqual(self.call("post", f"sessions/{self.session.id}/guests/", {"enrollment_id": self.e1.id}).status_code, 400)
        self.call("post", f"sessions/{self.session.id}/close/")
        self.assertEqual(self.add().status_code, 400)

    def test_target_must_be_one_of_his_own_open_or_planned_sessions(self):
        other_group_session = SessionInstance.objects.create(
            environment=self.env_a, group=self.g1, scheduled_at=NOW + dt.timedelta(days=2))
        self.assertEqual(self.add(home_session_id=other_group_session.id).status_code, 400)
        self.assertEqual(self.add(home_session_id="abc").status_code, 400)
        self.assertEqual(self.add(home_session_id=self.home.id).status_code, 201)

    def test_visit_can_be_cancelled_until_it_has_been_carried(self):
        self.add(); self.guest(attendance="present")
        self.assertEqual(self.call("delete", f"sessions/{self.session.id}/guests/{self.e3.id}/").status_code, 204)
        self.add(); self.guest(attendance="present"); self.open_home()
        self.assertEqual(self.call("delete", f"sessions/{self.session.id}/guests/{self.e3.id}/").status_code, 400)

    def test_edits_after_his_session_has_closed_are_refused(self):
        self.open_home(); self.add(); self.guest(attendance="present")
        self.call("post", f"sessions/{self.home.id}/close/")
        r = self.guest(attendance="absent")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(AttendanceRecord.objects.get(session=self.home, enrollment=self.e3).status, "present")

    def test_candidates_exclude_members_and_show_upcoming_sessions(self):
        rows = self.call("get", f"sessions/{self.session.id}/guest-candidates/").data["results"]
        self.assertEqual([r["enrollment_id"] for r in rows], [self.e3.id])
        self.assertEqual(rows[0]["upcoming"][0]["id"], self.home.id)
        self.assertEqual(self.call("get", f"sessions/{self.session.id}/guest-candidates/?q=zzz").data["results"], [])

    def test_roster_lists_the_guest_but_counts_only_members(self):
        self.add(); self.guest(attendance="present")
        roster = self.call("get", f"sessions/{self.session.id}/roster/").data
        self.assertEqual([g["enrollment_id"] for g in roster["guests"]], [self.e3.id])
        self.assertEqual(roster["counts"]["total"], 2)
        self.assertEqual(roster["counts"]["present"], 0)

    def test_scanning_his_badge_at_another_groups_session_records_a_visit(self):
        r = self.call("post", "scan/attendance/", {"token": self.e3.qr_token, "session_id": self.session.id, "status": "present"})
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["attendance"], "present")
        self.assertEqual(r.data["guest"]["home_session"]["id"], self.home.id)
        self.assertFalse(AttendanceRecord.objects.filter(session=self.session, enrollment=self.e3).exists())
        self.open_home()
        self.assertTrue(AttendanceRecord.objects.filter(session=self.home, enrollment=self.e3).exists())

    def test_another_teacher_cannot_add_guests_to_my_session(self):
        r = self.call("post", f"sessions/{self.session.id}/guests/", {"enrollment_id": self.e3.id},
                      client=self.client_b, env=self.env_b)
        self.assertEqual(r.status_code, 404)
        self.assertFalse(GuestVisit.objects.exists())


class DeleteSessionTests(Base):
    def url(self, s=None):
        return f"sessions/{(s or self.session).id}/"

    def test_a_planned_session_can_be_deleted(self):
        self.assertEqual(self.call("delete", self.url()).status_code, 204)
        self.assertFalse(SessionInstance.objects.filter(pk=self.session.pk).exists())

    def test_an_opened_session_with_no_marks_can_be_deleted(self):
        self.open()
        self.assertEqual(self.call("delete", self.url()).status_code, 204)

    def test_a_session_with_attendance_or_recitation_is_protected(self):
        self.open()
        self.mark("attendance", self.e1, "present")
        r = self.call("delete", self.url())
        self.assertEqual(r.status_code, 400)
        self.assertTrue(SessionInstance.objects.filter(pk=self.session.pk).exists())
        self.assertEqual(AttendanceRecord.objects.count(), 1)

    def test_a_session_holding_a_guests_marks_is_protected(self):
        self.open()
        other = make_enrollment(self.env_a, self.make_student_in(self.env_a, "201010100009", name="ز"), self.grade, self.g2)
        self.call("post", "scan/attendance/", {"token": other.qr_token, "session_id": self.session.id, "status": "present"})
        self.assertEqual(self.call("delete", self.url()).status_code, 400)

    def test_deleting_the_target_session_frees_the_visit_for_the_next_one(self):
        e3 = make_enrollment(self.env_a, self.make_student_in(self.env_a, "201010100003", name="ض"), self.grade, self.g2)
        home = SessionInstance.objects.create(environment=self.env_a, group=self.g2, scheduled_at=NOW + dt.timedelta(days=4))
        self.open()
        self.call("post", f"sessions/{self.session.id}/guests/", {"enrollment_id": e3.id})
        self.call("put", f"sessions/{self.session.id}/guests/{e3.id}/", {"attendance": "present"})
        self.assertEqual(self.call("delete", self.url(home)).status_code, 204)
        self.assertIsNone(GuestVisit.objects.get().home_session)

    def test_another_teacher_cannot_delete_my_session(self):
        r = self.call("delete", self.url(), client=self.client_b, env=self.env_b)
        self.assertEqual(r.status_code, 404)
        self.assertTrue(SessionInstance.objects.filter(pk=self.session.pk).exists())
