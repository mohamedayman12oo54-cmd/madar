"""Student Area: what a student may see/do, and — as important — what they may
NOT (other students, other teachers, drafts, private notes, answers before
submitting)."""
from decimal import Decimal

from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import Grade, Group
from accounts.testing import make_enrollment
from config.months import current_month
from content.models import ContentItem
from environments.tenancy_testing import PASSWORD, TenantTestCase
from evaluation.models import MonthlyRating, PrivateNote, StudentState
from financials.models import MonthlyPayment
from notifications.models import Notification
from scheduling.models import AttendanceRecord, RecitationRecord, SessionInstance

from .models import Quiz, QuizAttempt

S = "/api/v1/student/"
LESSON = ("الخلية هي الوحدة الأساسية في بناء جميع الكائنات الحية. "
          "تحتوي الخلية النباتية على جدار خلوي يحيط بالغشاء البلازمي. "
          "تقوم البلاستيدات الخضراء بعملية البناء الضوئي داخل الخلية النباتية. "
          "يحتوي النواة على المادة الوراثية التي تتحكم في نشاط الخلية.")


class Base(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=Decimal("100"))
        self.other_grade = Grade.objects.create(environment=self.env_a, name="ثاني", fee_amount=Decimal("100"))
        self.g1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.me, self.e1 = self.student(self.env_a, "201555500001", "أحمد", self.grade, self.g1)
        self.peer, self.e2 = self.student(self.env_a, "201555500002", "سارة", self.grade, self.g1)

    def student(self, env, phone, name, grade, group=None):
        user = self.make_student_in(env, phone, name)
        user.is_active = True
        user.set_password(PASSWORD)
        user.save()
        enrollment = make_enrollment(env, user, grade, group)
        client = APIClient()
        tok = client.post("/api/v1/auth/student/login/", {"phone": "+" + phone, "password": PASSWORD}).data["access"]
        client.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        return client, enrollment

    def get(self, path, client=None, env=None):
        return (client or self.me).get(S + path, **self.with_env((env or self.env_a).id))

    def post(self, path, body=None, client=None, env=None):
        return (client or self.me).post(S + path, body or {}, format="json", **self.with_env((env or self.env_a).id))

    def video(self, **kw):
        defaults = dict(environment=self.env_a, title="درس الخلية", description=LESSON, video_provider="youtube",
                        video_ref="dQw4w9WgXcQ", published_at=timezone.now())
        defaults.update(kw)
        item = ContentItem.objects.create(**defaults)
        return item


class AccessRulesTests(Base):
    def test_every_endpoint_rejects_a_teacher_and_a_missing_environment(self):
        for path in ("overview/", "attendance/", "recitation/", "payments/", "evaluation/", "videos/", "notifications/", "quizzes/"):
            self.assertEqual(self.client_a.get(S + path, **self.with_env(self.env_a.id)).status_code, 403, path)
            self.assertIn(self.me.get(S + path).status_code, (400, 403), path)  # no X-Environment-ID header

    def test_student_cannot_use_another_teachers_environment(self):
        self.assertEqual(self.get("overview/", env=self.env_b).status_code, 403)

    def test_a_deactivated_student_loses_access_immediately(self):
        self.assertEqual(self.get("overview/").status_code, 200)
        self.e1.is_active = False
        self.e1.save()
        self.assertEqual(self.get("overview/").status_code, 401)


class OwnRecordsTests(Base):
    def setUp(self):
        super().setUp()
        self.session = SessionInstance.objects.create(environment=self.env_a, group=self.g1, scheduled_at=timezone.now(), status="closed")
        AttendanceRecord.objects.create(environment=self.env_a, session=self.session, enrollment=self.e1, status="present")
        AttendanceRecord.objects.create(environment=self.env_a, session=self.session, enrollment=self.e2, status="absent")
        RecitationRecord.objects.create(environment=self.env_a, session=self.session, enrollment=self.e1, status="not_studied")

    def test_attendance_and_recitation_are_only_mine(self):
        a = self.get("attendance/").json()
        self.assertEqual(a["summary"], {"present": 1, "absent": 0})
        self.assertEqual([r["status"] for r in a["results"]], ["present"])
        r = self.get("recitation/").json()
        self.assertEqual(r["summary"], {"studied": 0, "not_studied": 1})
        peer = self.get("attendance/", client=self.peer).json()
        self.assertEqual([x["status"] for x in peer["results"]], ["absent"])

    def test_payments_show_status_only_never_amounts_and_unrecorded_is_unpaid(self):
        MonthlyPayment.objects.create(environment=self.env_a, enrollment=self.e1, month=current_month(), status="paid", amount=Decimal("100"))
        rows = self.get("payments/").json()["results"]
        self.assertEqual(rows[0], {"month": current_month().strftime("%Y-%m"), "status": "paid"})
        self.assertEqual(self.get("payments/", client=self.peer).json()["results"][0]["status"], "unpaid")
        self.assertNotIn("amount", self.get("payments/").content.decode())

    def test_only_published_rating_and_finalized_state_are_visible(self):
        m = current_month()
        StudentState.objects.create(environment=self.env_a, enrollment=self.e1, month=m, state="at_risk")
        MonthlyRating.objects.create(environment=self.env_a, enrollment=self.e1, month=m, value=2)  # DRAFT
        row = self.get("evaluation/").json()["results"][0]
        self.assertEqual((row["state"], row["rating"]), ("at_risk", None))
        MonthlyRating.objects.filter(enrollment=self.e1).update(published_at=timezone.now())
        self.assertEqual(self.get("evaluation/").json()["results"][0]["rating"], 2)
        self.assertEqual(self.get("evaluation/", client=self.peer).json()["results"], [])

    def test_private_teacher_notes_never_leak_anywhere(self):
        PrivateNote.objects.create(environment=self.env_a, enrollment=self.e1, body="سرّي-جدًا-XYZ")
        for path in ("overview/", "attendance/", "recitation/", "payments/", "evaluation/", "videos/", "notifications/", "quizzes/"):
            self.assertNotIn("سرّي-جدًا-XYZ", self.get(path).content.decode(), path)

    def test_overview_summary(self):
        body = self.get("overview/").json()
        self.assertEqual((body["student"]["name"], body["grade"], body["groups"]), ("أحمد", "أول", ["G1"]))
        self.assertEqual(body["this_month"]["attendance"], {"present": 1, "absent": 0})

    def test_student_sees_the_teacher_scoped_name_not_other_teachers(self):
        self.e1.student_name = "اسم عند المعلم أ"
        self.e1.save()
        self.assertEqual(self.get("overview/").json()["student"]["name"], "اسم عند المعلم أ")


class VideoVisibilityTests(Base):
    def test_only_published_and_targeted_videos_are_visible(self):
        visible = self.video(title="لمجموعتي")
        visible.target_groups.add(self.g1)
        by_grade = self.video(title="لصفي")
        by_grade.target_grades.add(self.grade)
        direct = self.video(title="لي وحدي")
        direct.target_enrollments.add(self.e1)
        draft = self.video(title="مسودة", published_at=None)
        draft.target_grades.add(self.grade)
        other_grade = self.video(title="صف آخر")
        other_grade.target_grades.add(self.other_grade)
        untargeted = self.video(title="بلا مستهدفين")
        titles = {v["title"] for v in self.get("videos/").json()["results"]}
        self.assertEqual(titles, {"لمجموعتي", "لصفي", "لي وحدي"})
        self.assertEqual({v["title"] for v in self.get("videos/", client=self.peer).json()["results"]}, {"لمجموعتي", "لصفي"})

    def test_the_stored_video_reference_is_never_exposed(self):
        self.video().target_grades.add(self.grade)
        body = self.get("videos/").content.decode()
        self.assertNotIn("dQw4w9WgXcQ\"", body.replace("embed/dQw4w9WgXcQ", ""))
        self.assertNotIn("video_ref", body)

    def test_another_teachers_content_is_invisible(self):
        item = ContentItem.objects.create(environment=self.env_b, title="ب", published_at=timezone.now())
        self.assertEqual(self.get("videos/").json()["results"], [])


class NotificationTests(Base):
    def setUp(self):
        super().setUp()
        self.n1 = Notification.objects.create(environment=self.env_a, recipient=self.e1.student, enrollment=self.e1, type="absent", title="غياب")
        self.n2 = Notification.objects.create(environment=self.env_a, recipient=self.e2.student, enrollment=self.e2, type="absent", title="لزميلي")

    def test_only_my_notifications_and_unread_count(self):
        body = self.get("notifications/").json()
        self.assertEqual([n["title"] for n in body["results"]], ["غياب"])
        self.assertEqual(self.get("overview/").json()["unread_notifications"], 1)

    def test_mark_read_only_mine(self):
        self.assertEqual(self.post(f"notifications/{self.n1.id}/read/").status_code, 200)
        self.assertEqual(self.get("overview/").json()["unread_notifications"], 0)
        self.assertEqual(self.post(f"notifications/{self.n2.id}/read/").status_code, 404)
        self.n2.refresh_from_db()
        self.assertIsNone(self.n2.read_at)

    def test_read_all_touches_only_my_rows(self):
        self.assertEqual(self.post("notifications/read-all/").json()["marked"], 1)
        self.n2.refresh_from_db()
        self.assertIsNone(self.n2.read_at)

    def test_a_notification_fired_before_the_student_claimed_waits_in_their_inbox(self):
        # fired for an enrollment whose account was still unclaimed -> same row, visible after claiming
        self.assertEqual(Notification.objects.filter(recipient=self.e1.student).count(), 1)
        self.assertEqual(len(self.get("notifications/").json()["results"]), 1)


class QuizTests(Base):
    def setUp(self):
        super().setUp()
        self.item = self.video(quiz_source="")
        self.item.target_grades.add(self.grade)

    def request(self, **kw):
        return self.post("quizzes/", {"content_id": self.item.id, **kw})

    def generate(self, **kw):
        r = self.request(**kw)
        self.assertIn(r.status_code, (200, 202), r.content)
        call_command("process_ai_operations")
        return self.get(f"quizzes/operations/{r.json()['id']}/").json()

    def test_full_flow_generation_is_async_and_the_quiz_is_persisted_before_answering(self):
        r = self.request()
        self.assertEqual((r.status_code, r.json()["status"], r.json()["quiz_id"]), (202, "pending", None))
        self.assertEqual(Quiz.objects.count(), 0)               # nothing exists until the worker succeeds
        call_command("process_ai_operations")
        op = self.get(f"quizzes/operations/{r.json()['id']}/").json()
        self.assertEqual(op["status"], "completed")
        self.assertEqual(Quiz.objects.count(), 1)
        detail = self.get(f"quizzes/{op['quiz_id']}/").json()
        self.assertFalse(detail["submitted"])
        self.assertTrue(all("answer_index" not in q and "explanation" not in q for q in detail["questions"]))  # no answers before submit

    def test_submit_is_auto_scored_server_side_reveals_answers_and_is_single_attempt(self):
        op = self.generate()
        quiz = Quiz.objects.get(pk=op["quiz_id"])
        answers = [q["answer_index"] for q in quiz.questions]
        answers[0] = (answers[0] + 1) % len(quiz.questions[0]["options"])  # one wrong on purpose
        r = self.post(f"quizzes/{quiz.id}/submit/", {"answers": answers})
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertEqual((body["score"], body["total"]), (len(answers) - 1, len(answers)))
        self.assertTrue(all("answer_index" in q for q in body["questions"]))
        self.assertEqual(self.post(f"quizzes/{quiz.id}/submit/", {"answers": answers}).status_code, 409)
        self.assertEqual(QuizAttempt.objects.count(), 1)
        listed = self.get("quizzes/").json()["results"][0]
        self.assertEqual((listed["score"], listed["total"]), (body["score"], body["total"]))

    def test_malformed_answers_rejected(self):
        quiz = Quiz.objects.get(pk=self.generate()["quiz_id"])
        n = len(quiz.questions)
        for bad in ([], [0] * (n + 1), [99] + [0] * (n - 1), [-1] + [0] * (n - 1)):
            self.assertEqual(self.post(f"quizzes/{quiz.id}/submit/", {"answers": bad}).status_code, 400, bad)
        self.assertEqual(QuizAttempt.objects.count(), 0)

    def test_skipping_questions_counts_as_wrong(self):
        quiz = Quiz.objects.get(pk=self.generate()["quiz_id"])
        r = self.post(f"quizzes/{quiz.id}/submit/", {"answers": [None] * len(quiz.questions)})
        self.assertEqual(r.json()["score"], 0)

    def test_a_failed_generation_leaves_no_quiz_and_a_clear_error(self):
        short = self.video(title="قصير", description="جملة قصيرة جدًا هنا.")
        short.target_grades.add(self.grade)
        r = self.post("quizzes/", {"content_id": short.id})
        call_command("process_ai_operations")
        op = self.get(f"quizzes/operations/{r.json()['id']}/").json()
        self.assertEqual((op["status"], op["quiz_id"]), ("failed", None))
        self.assertTrue(op["error"])
        self.assertEqual(Quiz.objects.count(), 0)

    def test_idempotent_submission_and_conflicting_reuse(self):
        a = self.request(idempotency_key="k1")
        b = self.request(idempotency_key="k1")
        self.assertEqual((a.status_code, b.status_code, a.json()["id"] == b.json()["id"]), (202, 200, True))
        other = self.video(title="آخر")
        other.target_grades.add(self.grade)
        self.assertEqual(self.post("quizzes/", {"content_id": other.id, "idempotency_key": "k1"}).status_code, 409)

    def test_cannot_request_a_quiz_on_content_not_targeted_at_me_or_not_published(self):
        hidden = self.video(title="مخفي")
        self.assertEqual(self.post("quizzes/", {"content_id": hidden.id}).status_code, 404)
        draft = self.video(published_at=None)
        draft.target_grades.add(self.grade)
        self.assertEqual(self.post("quizzes/", {"content_id": draft.id}).status_code, 404)
        foreign = ContentItem.objects.create(environment=self.env_b, title="ب", description=LESSON, published_at=timezone.now())
        self.assertEqual(self.post("quizzes/", {"content_id": foreign.id}).status_code, 404)

    def test_quizzes_and_operations_are_private_to_their_owner(self):
        op = self.generate()
        self.assertEqual(self.get(f"quizzes/{op['quiz_id']}/", client=self.peer).status_code, 404)
        self.assertEqual(self.post(f"quizzes/{op['quiz_id']}/submit/", {"answers": [0]}, client=self.peer).status_code, 404)
        self.assertEqual(self.get("quizzes/", client=self.peer).json()["results"], [])
        self.assertEqual(self.get(f"quizzes/operations/{op['id']}/", client=self.peer).status_code, 404)

    def test_only_teacher_provided_material_is_snapshotted_for_the_model(self):
        r = self.request()
        evidence = AIOp.objects.get(pk=r.json()["id"]).evidence
        self.assertEqual(set(evidence), {"title", "text"})
        self.assertNotIn("أحمد", str(evidence))

    def test_generation_is_rate_limited(self):
        from unittest import mock

        from rest_framework.throttling import SimpleRateThrottle

        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"ai-submit": "1/hour"}):
            codes = [self.request().status_code for _ in range(2)]
        self.assertEqual(codes, [202, 429])


from ai.models import AIOperation as AIOp  # noqa: E402


class AssistantTests(Base):
    def curate(self, **kw):
        """The Study Assistant answers ONLY from the published central KB."""
        from knowledge.models import KBDocument

        doc = KBDocument.objects.create(**{
            "title": "الخلية", "topic": "أحياء",
            "body": "الخلية هي الوحدة البنائية والوظيفية الأساسية لجميع الكائنات الحية.",
            **kw})
        if kw.get("status") != "draft":
            doc.publish()
        return doc

    def test_student_can_ask_the_general_tutor_and_it_is_not_linked_to_any_record(self):
        self.curate()
        r = self.post("assistant/", {"prompt": "ما هي الخلية؟"})
        self.assertEqual(r.status_code, 202, r.content)
        call_command("process_ai_operations")
        op = self.get(f"assistant/{r.json()['id']}/").json()
        self.assertEqual(op["status"], "completed")
        row = AIOp.objects.get(pk=r.json()["id"])
        self.assertIsNone(row.enrollment_id)

    def test_answer_cites_the_published_knowledge_base_documents_it_used(self):
        doc = self.curate()
        r = self.post("assistant/", {"prompt": "ما هي الخلية؟"})
        call_command("process_ai_operations")
        op = self.get(f"assistant/{r.json()['id']}/").json()
        self.assertEqual(op["status"], "completed")
        self.assertEqual([s["id"] for s in op["sources"]], [doc.id])
        self.assertEqual(op["sources"][0]["title"], "الخلية")

    def test_draft_knowledge_is_never_used_as_a_source(self):
        """Only PUBLISHED content is authoritative for AI consumption."""
        self.curate(status="draft")
        r = self.post("assistant/", {"prompt": "ما هي الخلية؟"})
        call_command("process_ai_operations")
        op = self.get(f"assistant/{r.json()['id']}/").json()
        self.assertEqual(op["status"], "failed")
        self.assertEqual(op["sources"], [])

    def test_without_any_grounding_the_tutor_refuses_instead_of_inventing(self):
        r = self.post("assistant/", {"prompt": "موضوع لا تغطيه قاعدة المعرفة إطلاقًا"})
        call_command("process_ai_operations")
        op = self.get(f"assistant/{r.json()['id']}/").json()
        self.assertEqual(op["status"], "failed")
        self.assertEqual(op["result"], "")
        self.assertEqual(op["sources"], [])

    def test_assistant_history_is_private(self):
        r = self.post("assistant/", {"prompt": "سؤال خاص"})
        self.assertEqual(self.get(f"assistant/{r.json()['id']}/", client=self.peer).status_code, 404)
        self.assertEqual(self.get("assistant/", client=self.peer).json()["count"], 0)

    def test_a_teacher_cannot_use_the_student_assistant_endpoint(self):
        self.assertEqual(self.client_a.post(S + "assistant/", {"prompt": "x y"}, format="json", **self.with_env(self.env_a.id)).status_code, 403)
