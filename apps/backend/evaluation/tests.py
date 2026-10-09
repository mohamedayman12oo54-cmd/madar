"""Monthly State / Rating (draft -> publish) and teacher-private notes."""
from academics.models import Grade, Group
from accounts.testing import make_enrollment
from config.months import current_month
from environments.tenancy_testing import TenantTestCase
from notifications.models import Notification

from .models import MonthlyRating, PrivateNote, StudentState

E = "/api/v1/evaluation/"


class EvaluationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.month = current_month().strftime("%Y-%m")
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=1)
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.s1 = self.make_student_in(self.env_a, "201012200001", name="أحمد")
        self.e1 = make_enrollment(self.env_a, self.s1, self.grade, self.group)

    def put(self, path, body, client=None, env=None):
        return (client or self.client_a).put(E + path, body, format="json", **self.with_env((env or self.env_a).id))

    def post(self, path, body):
        return self.client_a.post(E + path, body, format="json", **self.with_env(self.env_a.id))

    def test_rating_is_1_to_5_only(self):
        for v in (0, 6, -1, "x"):
            self.assertEqual(self.put("ratings/", {"enrollment_id": self.e1.id, "month": self.month, "value": v}).status_code, 400, v)
        self.assertEqual(self.put("ratings/", {"enrollment_id": self.e1.id, "month": self.month, "value": 5}).status_code, 200)

    def test_rating_is_a_draft_until_published_and_publishing_notifies_exactly_once(self):
        self.put("ratings/", {"enrollment_id": self.e1.id, "month": self.month, "value": 4})
        self.assertEqual(Notification.objects.count(), 0)
        body = {"enrollment_id": self.e1.id, "month": self.month}
        self.assertEqual(self.post("ratings/publish/", body).status_code, 200)
        self.assertEqual(self.post("ratings/publish/", body).status_code, 409)
        n = Notification.objects.get()
        self.assertEqual((n.type, n.recipient_id), ("rating_published", self.s1.id))
        self.assertTrue(MonthlyRating.objects.get().published_at)

    def test_cannot_publish_a_rating_that_does_not_exist(self):
        self.assertEqual(self.post("ratings/publish/", {"enrollment_id": self.e1.id, "month": self.month}).status_code, 400)

    def test_publish_all_only_publishes_drafts(self):
        s2 = self.make_student_in(self.env_a, "201012200002", name="سارة")
        e2 = make_enrollment(self.env_a, s2, self.grade, self.group)
        for e in (self.e1, e2):
            self.put("ratings/", {"enrollment_id": e.id, "month": self.month, "value": 3})
        self.post("ratings/publish/", {"enrollment_id": self.e1.id, "month": self.month})
        r = self.post("ratings/publish-all/", {"month": self.month})
        self.assertEqual(r.json()["published"], 1)
        self.assertEqual(Notification.objects.filter(type="rating_published").count(), 2)

    def test_state_vocabulary_is_controlled(self):
        for bad in ("excellent", "", "GOOD"):
            self.assertEqual(self.put("states/", {"enrollment_id": self.e1.id, "month": self.month, "state": bad}).status_code, 400, bad)
        for ok in ("good", "needs_follow_up", "at_risk"):
            self.assertEqual(self.put("states/", {"enrollment_id": self.e1.id, "month": self.month, "state": ok}).status_code, 200)
        self.assertEqual(StudentState.objects.count(), 1)
        self.assertEqual(StudentState.objects.get().finalized_by_id, self.teacher_a.id)

    def test_monthly_sheet_reports_rating_state_and_evidence(self):
        self.put("ratings/", {"enrollment_id": self.e1.id, "month": self.month, "value": 2})
        self.put("states/", {"enrollment_id": self.e1.id, "month": self.month, "state": "at_risk"})
        row = self.client_a.get(f"{E}monthly/?month={self.month}", **self.with_env(self.env_a.id)).json()["rows"][0]
        self.assertEqual((row["rating"], row["state"]), ({"value": 2, "published": False}, "at_risk"))
        self.assertEqual(row["evidence"], {"present": 0, "absent": 0, "studied": 0, "not_studied": 0})
        self.assertIsNone(row["recommendation"])

    def test_notes_are_teacher_private_and_isolated(self):
        r = self.client_a.post(E + "notes/", {"enrollment_id": self.e1.id, "body": "يحتاج متابعة"}, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(PrivateNote.objects.get().author_id, self.teacher_a.id)
        self.assertEqual(self.client_b.get(E + "notes/", **self.with_env(self.env_b.id)).json()["count"], 0)
        nid = r.json()["id"]
        self.assertEqual(self.client_b.get(f"{E}notes/{nid}/", **self.with_env(self.env_b.id)).status_code, 404)
        self.assert_cross_tenant_denied("get", E + "notes/")

    def test_cannot_evaluate_another_teachers_student(self):
        r = self.put("ratings/", {"enrollment_id": self.e1.id, "month": self.month, "value": 3}, client=self.client_b, env=self.env_b)
        self.assertEqual(r.status_code, 404)
        self.assertEqual(MonthlyRating.objects.count(), 0)

    def test_state_recommendation_is_advisory_and_never_changes_the_state(self):
        from django.core.management import call_command

        from ai.models import AIOperation

        r = self.client_a.post("/api/v1/ai/state-recommendations/", {"enrollment_id": self.e1.id, "month": self.month},
                               format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 202, r.content)
        call_command("process_ai_operations")
        op = AIOperation.objects.get()
        self.assertEqual(op.status, "failed")  # no evidence this month -> explicit failure, nothing persisted elsewhere
        self.assertEqual(StudentState.objects.count(), 0)
        from scheduling.models import AttendanceRecord, SessionInstance
        from django.utils import timezone

        sess = SessionInstance.objects.create(environment=self.env_a, group=self.group, scheduled_at=timezone.now(), status="open")
        AttendanceRecord.objects.create(environment=self.env_a, session=sess, enrollment=self.e1, status="absent")
        self.client_a.post("/api/v1/ai/state-recommendations/", {"enrollment_id": self.e1.id, "month": self.month}, format="json", **self.with_env(self.env_a.id))
        call_command("process_ai_operations")
        op = AIOperation.objects.order_by("-id").first()
        self.assertEqual((op.status, op.suggested_state), ("completed", "at_risk"))
        self.assertEqual(StudentState.objects.count(), 0)  # only the teacher finalizes
        self.assertNotIn("name", op.evidence)
