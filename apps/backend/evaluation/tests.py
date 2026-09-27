"""Phase 4 — TeacherNote and Rating: minimum viable structure for "Student
Evaluation" (see models.py docstring for the flagged, unresolved grading
question this deliberately does NOT invent an answer to)."""
from django.core.exceptions import ValidationError as DjangoValidationError

from academics.models import Enrollment, Grade, Group
from environments.tenancy_testing import TenantTestCase
from scheduling.models import SessionInstance
from django.utils import timezone

from .models import Rating, TeacherNote

NOTES_URL = "/api/v1/evaluation/notes/"
RATINGS_URL = "/api/v1/evaluation/ratings/"


def note_url(pk):
    return f"{NOTES_URL}{pk}/"


def rating_url(pk):
    return f"{RATINGS_URL}{pk}/"


class EvaluationSetupMixin:
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.other_group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        self.student = self.make_student_in(self.env_a, "201150000001", name="أحمد")
        self.enrollment = Enrollment.objects.create(environment=self.env_a, student=self.student, grade=self.grade, group=self.group)
        self.session = SessionInstance.objects.create(environment=self.env_a, group=self.group, scheduled_at=timezone.now())
        self.other_group_session = SessionInstance.objects.create(environment=self.env_a, group=self.other_group, scheduled_at=timezone.now())

        grade_b = Grade.objects.create(environment=self.env_b, name="أول")
        student_b = self.make_student_in(self.env_b, "201150000002", name="X")
        self.enrollment_b = Enrollment.objects.create(environment=self.env_b, student=student_b, grade=grade_b)


class TeacherNoteTests(EvaluationSetupMixin, TenantTestCase):
    def test_create_general_note(self):
        r = self.client_a.post(NOTES_URL, {"enrollment_id": self.enrollment.id, "body": "طالب مجتهد"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertIsNone(r.json()["session"])
        self.assertEqual(r.json()["student"]["name"], "أحمد")

    def test_create_session_scoped_note(self):
        r = self.client_a.post(
            NOTES_URL, {"enrollment_id": self.enrollment.id, "session_id": self.session.id, "body": "تسميع ممتاز"},
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["session"], self.session.id)

    def test_blank_body_rejected(self):
        r = self.client_a.post(NOTES_URL, {"enrollment_id": self.enrollment.id, "body": "   "}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_session_from_a_different_group_rejected(self):
        r = self.client_a.post(
            NOTES_URL, {"enrollment_id": self.enrollment.id, "session_id": self.other_group_session.id, "body": "x"},
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 400)
        self.assertIn("session_id", r.json()["fields"])

    def test_cannot_note_another_teachers_enrollment(self):
        r = self.client_a.post(NOTES_URL, {"enrollment_id": self.enrollment_b.id, "body": "x"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)
        self.assertFalse(TeacherNote.objects.filter(enrollment=self.enrollment_b).exists())

    def test_list_filter_by_enrollment_and_session(self):
        TeacherNote.objects.create(environment=self.env_a, enrollment=self.enrollment, body="عام")
        TeacherNote.objects.create(environment=self.env_a, enrollment=self.enrollment, session=self.session, body="تسميع")
        r = self.client_a.get(f"{NOTES_URL}?session_id={self.session.id}", **self.with_env(self.env_a.id))
        self.assertEqual(len(r.json()["results"]), 1)

    def test_update_body_only(self):
        n = TeacherNote.objects.create(environment=self.env_a, enrollment=self.enrollment, body="قديم")
        r = self.client_a.patch(note_url(n.id), {"body": "جديد"}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        n.refresh_from_db()
        self.assertEqual(n.body, "جديد")

    def test_delete_note(self):
        n = TeacherNote.objects.create(environment=self.env_a, enrollment=self.enrollment, body="x")
        r = self.client_a.delete(note_url(n.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 204)

    def test_cannot_read_update_or_delete_another_teachers_note(self):
        n = TeacherNote.objects.create(environment=self.env_a, enrollment=self.enrollment, body="سري")
        self.assert_cross_tenant_denied("get", note_url(n.id))
        self.assert_cross_tenant_denied("patch", note_url(n.id), body={"body": "x"})
        self.assert_cross_tenant_denied("delete", note_url(n.id))

    def test_model_level_clean_rejects_cross_group_session(self):
        note = TeacherNote(environment=self.env_a, enrollment=self.enrollment, session=self.other_group_session, body="x")
        with self.assertRaises(DjangoValidationError):
            note.clean()


class RatingTests(EvaluationSetupMixin, TenantTestCase):
    def test_create_rating(self):
        r = self.client_a.post(RATINGS_URL, {"enrollment_id": self.enrollment.id, "value": 4}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["value"], 4)

    def test_value_out_of_range_rejected(self):
        for bad in (0, 6, -1):
            r = self.client_a.post(RATINGS_URL, {"enrollment_id": self.enrollment.id, "value": bad}, **self.with_env(self.env_a.id))
            self.assertEqual(r.status_code, 400, bad)

    def test_session_scoped_rating_must_match_enrollments_group(self):
        r = self.client_a.post(
            RATINGS_URL, {"enrollment_id": self.enrollment.id, "session_id": self.other_group_session.id, "value": 3},
            **self.with_env(self.env_a.id),
        )
        self.assertEqual(r.status_code, 400)

    def test_update_value(self):
        rt = Rating.objects.create(environment=self.env_a, enrollment=self.enrollment, value=2)
        r = self.client_a.patch(rating_url(rt.id), {"value": 5}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        rt.refresh_from_db()
        self.assertEqual(rt.value, 5)

    def test_update_value_out_of_range_rejected(self):
        rt = Rating.objects.create(environment=self.env_a, enrollment=self.enrollment, value=2)
        r = self.client_a.patch(rating_url(rt.id), {"value": 9}, **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 400)

    def test_cannot_read_update_or_delete_another_teachers_rating(self):
        rt = Rating.objects.create(environment=self.env_a, enrollment=self.enrollment, value=3)
        self.assert_cross_tenant_denied("get", rating_url(rt.id))
        self.assert_cross_tenant_denied("patch", rating_url(rt.id), body={"value": 1})
        self.assert_cross_tenant_denied("delete", rating_url(rt.id))

    def test_list_filter_by_enrollment(self):
        Rating.objects.create(environment=self.env_a, enrollment=self.enrollment, value=3)
        r = self.client_a.get(f"{RATINGS_URL}?enrollment_id={self.enrollment.id}", **self.with_env(self.env_a.id))
        self.assertEqual(len(r.json()["results"]), 1)
