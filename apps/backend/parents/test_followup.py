"""Guardian follow-up: the child's exam scores, and the teacher's warnings to the guardian."""
from datetime import timedelta

from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import Enrollment
from learning.models import Attempt, Exam

from .models import GuardianMessage
from .tests import GUARDIAN, OVERVIEW, _Base

SEND = "/api/v1/guardian-messages/"


def make_exam(env, enrollment, title="امتحان", *, opens=None, closes=None, published=True):
    exam = Exam.objects.create(
        environment=env, title=title, published_at=timezone.now() if published else None,
        opens_at=opens, closes_at=closes or timezone.now() + timedelta(days=1))
    exam.target_enrollments.add(enrollment)
    return exam


def sit(exam, enrollment, number, score, max_score=10, *, finished=True, deadline=None):
    now = timezone.now()
    return Attempt.objects.create(
        exam=exam, enrollment=enrollment, number=number, deadline_at=deadline or now + timedelta(minutes=30),
        submitted_at=now if finished else None, score=score if finished else None,
        max_score=max_score if finished else None)


class GuardianExamScoreTests(_Base):
    def exams(self):
        r = self.portal().get(OVERVIEW)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["exams"]

    def test_the_guardian_sees_the_score_that_counts(self):
        exam = make_exam(self.env_a, self.enr, "امتحان الوحدة الأولى")
        sit(exam, self.enr, 1, 4)
        sit(exam, self.enr, 2, 9)  # a re-sit the teacher allowed: the best one counts
        data = self.exams()
        self.assertEqual(data["finished"], 1)
        self.assertEqual(data["average_percent"], 90.0)
        row = data["results"][0]
        self.assertEqual((row["title"], row["state"], row["score"], row["max_score"], row["percent"]),
                         ("امتحان الوحدة الأولى", "finished", 9.0, 10.0, 90.0))

    def test_states_for_exams_the_child_has_not_finished(self):
        open_exam = make_exam(self.env_a, self.enr, "مفتوح")
        gone = make_exam(self.env_a, self.enr, "فات", closes=timezone.now() - timedelta(hours=1))
        running = make_exam(self.env_a, self.enr, "جارٍ")
        sit(running, self.enr, 1, 0, finished=False)
        states = {r["title"]: r["state"] for r in self.exams()["results"]}
        self.assertEqual(states, {"مفتوح": "not_taken", "فات": "missed", "جارٍ": "in_progress"})
        self.assertIsNone(self.exams()["average_percent"])

    def test_an_abandoned_sitting_is_reported_not_graded_by_a_page_view(self):
        exam = make_exam(self.env_a, self.enr, "ترك", closes=timezone.now() - timedelta(hours=1))
        stale = sit(exam, self.enr, 1, 0, finished=False, deadline=timezone.now() - timedelta(minutes=5))
        self.assertEqual(self.exams()["results"][0]["state"], "missed")
        stale.refresh_from_db()
        self.assertIsNone(stale.submitted_at, "the read-only portal must not close or grade a sitting")

    def test_upcoming_and_draft_exams_are_not_shown(self):
        make_exam(self.env_a, self.enr, "قادم", opens=timezone.now() + timedelta(days=1))
        make_exam(self.env_a, self.enr, "مسودة", published=False)
        self.assertEqual(self.exams()["results"], [])

    def test_another_childs_or_teachers_exam_never_appears(self):
        sibling_user = self.make_student_in(self.env_a, "201555800010", "زميل")
        self.activate(sibling_user)
        sibling = Enrollment.objects.create(
            environment=self.env_a, student=sibling_user, grade=self.grade, student_name="زميل",
            parent_phone="201099000444")
        theirs = make_exam(self.env_a, sibling, "للزميل فقط")
        sit(theirs, sibling, 1, 10)
        foreign = Exam.objects.create(environment=self.env_b, title="معلم آخر", published_at=timezone.now(),
                                      closes_at=timezone.now() + timedelta(days=1))
        foreign.target_grades.add(self.grade)
        self.assertEqual(self.exams()["results"], [])


class GuardianMessageTests(_Base):
    def send(self, client=None, **over):
        body = {"enrollment_id": self.enr.id, "kind": "warning", "title": "غياب متكرر",
                "body": "غاب ثلاث حصص هذا الشهر.", **over}
        return (client or self.client_a).post(SEND, body, format="json", **self.with_env(self.env_a.id))

    def test_a_warning_reaches_the_guardian_portal_and_not_the_students_inbox(self):
        r = self.send()
        self.assertEqual(r.status_code, 201, r.content)
        self.assertTrue(r.json()["guardian_can_view"])
        msgs = self.portal().get(OVERVIEW).json()["messages"]
        self.assertEqual([(m["kind"], m["kind_label"], m["title"], m["body"]) for m in msgs],
                         [("warning", "تحذير", "غياب متكرر", "غاب ثلاث حصص هذا الشهر.")])
        from notifications.models import Notification
        self.assertFalse(Notification.objects.filter(recipient=self.student, title="غياب متكرر").exists())

    def test_a_guardian_sees_only_messages_about_their_own_child(self):
        other_user = self.make_student_in(self.env_a, "201555800011", "زميل")
        self.activate(other_user)
        other = Enrollment.objects.create(
            environment=self.env_a, student=other_user, grade=self.grade, student_name="زميل",
            parent_phone="201099000555")
        self.send(enrollment_id=other.id, title="سر الزميل")
        self.assertEqual(self.portal().get(OVERVIEW).json()["messages"], [])
        self.assertEqual(len(self.portal(other).get(OVERVIEW).json()["messages"]), 1)

    def test_a_student_without_a_guardian_phone_cannot_be_messaged(self):
        self.enr.parent_phone = ""
        self.enr.save(update_fields=["parent_phone"])
        r = self.send()
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "no_guardian_phone")
        self.assertEqual(GuardianMessage.objects.count(), 0)

    def test_the_teacher_is_told_when_the_guardian_cannot_open_the_portal_yet(self):
        self.student.is_verified = False
        self.student.save(update_fields=["is_verified"])
        r = self.send()
        self.assertEqual(r.status_code, 201)
        self.assertFalse(r.json()["guardian_can_view"])

    def test_another_teacher_cannot_message_my_students_guardian(self):
        # their own environment header + my enrollment id in the body: the id is unknown in THEIR environment
        r = self.client_b.post(SEND, {"enrollment_id": self.enr.id, "title": "x", "body": "y"},
                               format="json", **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)
        # naming my environment is refused outright
        self.assert_cross_tenant_denied("post", SEND, body={"enrollment_id": self.enr.id, "title": "x", "body": "y"})
        self.assertEqual(GuardianMessage.objects.count(), 0)

    def test_history_is_per_student_and_environment_scoped(self):
        self.send(title="الأولى")
        self.send(title="الثانية", kind="note")
        r = self.client_a.get(SEND, {"enrollment": self.enr.id}, **self.with_env(self.env_a.id))
        self.assertEqual([m["title"] for m in r.json()["results"]], ["الثانية", "الأولى"])
        r = self.client_b.get(SEND, {"enrollment": self.enr.id}, **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)

    def test_validation(self):
        self.assertEqual(self.send(title="").status_code, 400)
        self.assertEqual(self.send(body="   ").status_code, 400)
        self.assertEqual(self.send(body="س" * 1001).status_code, 400)
        self.assertEqual(self.send(kind="spam").status_code, 400)

    def test_a_guardian_cannot_send_or_read_the_teachers_endpoint(self):
        guardian = self.portal()
        self.assertEqual(guardian.post(SEND, {"enrollment_id": self.enr.id, "title": "x", "body": "y"}).status_code, 403)
        self.assertEqual(guardian.get(SEND, {"enrollment": self.enr.id}).status_code, 403)
        self.assertEqual(APIClient().post(SEND, {}).status_code, 401)


class MessageReadReceiptTests(_Base):
    def send(self, **over):
        body = {"enrollment_id": self.enr.id, "kind": "warning", "title": "تحذير", "body": "نص", **over}
        r = self.client_a.post(SEND, body, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def read_url(self, pk):
        return f"/api/v1/parent/messages/{pk}/read/"

    def history(self):
        r = self.client_a.get(SEND, {"enrollment": self.enr.id}, **self.with_env(self.env_a.id))
        return r.json()["results"]

    def test_a_new_message_is_unread_until_the_guardian_opens_it(self):
        pk = self.send()
        self.assertIsNone(self.portal().get(OVERVIEW).json()["messages"][0]["read_at"])
        self.assertIsNone(self.history()[0]["read_at"])
        r = self.portal().post(self.read_url(pk))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIsNotNone(r.json()["read_at"])
        self.assertIsNotNone(self.history()[0]["read_at"], "the teacher can now see it was read")
        self.assertIsNotNone(self.portal().get(OVERVIEW).json()["messages"][0]["read_at"])

    def test_reading_twice_keeps_the_first_time(self):
        pk = self.send()
        first = self.portal().post(self.read_url(pk)).json()["read_at"]
        second = self.portal().post(self.read_url(pk)).json()["read_at"]
        self.assertEqual(first, second)

    def test_a_guardian_cannot_mark_another_childs_message(self):
        other_user = self.make_student_in(self.env_a, "201555800030", "زميل")
        self.activate(other_user)
        other = Enrollment.objects.create(environment=self.env_a, student=other_user, grade=self.grade,
                                          student_name="زميل", parent_phone="201099000888")
        pk = self.send(enrollment_id=other.id)
        self.assertEqual(self.portal().post(self.read_url(pk)).status_code, 404)
        self.assertIsNone(GuardianMessage.objects.get(pk=pk).read_at)

    def test_nobody_but_a_guardian_can_mark_a_message(self):
        pk = self.send()
        self.assertEqual(APIClient().post(self.read_url(pk)).status_code, 401)
        teacher = self.client_a.post(self.read_url(pk), **self.with_env(self.env_a.id))
        self.assertIn(teacher.status_code, (401, 403))
        self.assertIsNone(GuardianMessage.objects.get(pk=pk).read_at)

    def test_the_read_endpoint_changes_nothing_but_the_read_time(self):
        pk = self.send(title="العنوان", body="النص")
        self.portal().post(self.read_url(pk), {"title": "تم التغيير", "body": "x", "kind": "note"}, format="json")
        m = GuardianMessage.objects.get(pk=pk)
        self.assertEqual((m.title, m.body, m.kind), ("العنوان", "النص", "warning"))
        self.assertEqual(self.portal().get(self.read_url(pk)).status_code, 405)
