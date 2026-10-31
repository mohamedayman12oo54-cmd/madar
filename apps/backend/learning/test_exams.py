"""Secure exams: the server decides time, order, score and who may sit — never the browser."""
from datetime import timedelta
from decimal import Decimal
from unittest import mock

from django.core.cache import cache
from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import Grade, Group
from accounts.testing import make_enrollment
from environments.tenancy_testing import PASSWORD, TenantTestCase

from notifications.models import Notification

from .models import Attempt, AttemptGrant, Exam

T = "/api/v1/exams/"
S = "/api/v1/student/exams/"


def questions(n=3):
    return [{"text": f"سؤال {i}", "points": 2,
             "choices": [{"text": "صح", "is_correct": True}, {"text": "خطأ 1", "is_correct": False},
                         {"text": "خطأ 2", "is_correct": False}]} for i in range(n)]


class ExamBase(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=Decimal("100"))
        self.g1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.g2 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        self.me, self.e1 = self.student("201555500001", "أحمد", self.g1)
        self.peer, self.e2 = self.student("201555500002", "سارة", self.g2)

    def student(self, phone, name, group):
        user = self.make_student_in(self.env_a, phone, name)
        user.is_active = True
        user.set_password(PASSWORD)
        user.save()
        enrollment = make_enrollment(self.env_a, user, self.grade, group)
        c = APIClient()
        tok = c.post("/api/v1/auth/student/login/", {"phone": "+" + phone, "password": PASSWORD}).data["access"]
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        return c, enrollment

    def t(self, method, path, body=None, client=None):
        return getattr(client or self.client_a, method)(T + path, body or {}, format="json", **self.with_env(self.env_a.id))

    def s(self, method, path, body=None, client=None):
        return getattr(client or self.me, method)(S + path, body or {}, format="json", **self.with_env(self.env_a.id))

    def make_exam(self, publish=True, **kw):
        body = {"title": "امتحان", "duration_minutes": 20, "max_violations": 3, "questions": questions(),
                "group_ids": [self.g1.id], **kw}
        r = self.t("post", "", body)
        self.assertEqual(r.status_code, 201, r.content)
        eid = r.json()["id"]
        if publish:
            self.assertEqual(self.t("post", f"{eid}/publish/").status_code, 200)
        return eid

    def answer_all(self, eid, correct=True):
        st = self.s("post", f"{eid}/start/").json()
        for i in range(st["total"]):
            q = self.s("get", f"{eid}/question/{i}/").json()
            truth = Exam.objects.get(pk=eid).questions.get(pk=q["question_id"]).choices.get(is_correct=True).pk
            wrong = next(c["id"] for c in q["choices"] if c["id"] != truth)
            r = self.s("post", f"{eid}/answer/", {"question_id": q["question_id"], "choice_id": truth if correct else wrong})
            self.assertEqual(r.status_code, 200, r.content)


class TeacherSideTests(ExamBase):
    def test_validation(self):
        bad = questions(1)
        bad[0]["choices"][1]["is_correct"] = True
        self.assertEqual(self.t("post", "", {"title": "x", "questions": bad}).status_code, 400)
        self.assertEqual(self.t("post", "", {"title": "x", "questions": []}).status_code, 400)
        one = questions(1); one[0]["choices"] = one[0]["choices"][:1]
        self.assertEqual(self.t("post", "", {"title": "x", "questions": one}).status_code, 400)

    def test_cannot_publish_without_audience_and_other_teacher_cannot_touch(self):
        eid = self.make_exam(publish=False, group_ids=[])
        self.assertEqual(self.t("post", f"{eid}/publish/").status_code, 400)
        # Teacher B pointing at A's environment is refused outright; with his OWN environment the id is unknown.
        self.assertEqual(self.t("get", f"{eid}/", client=self.client_b).status_code, 403)
        own = self.client_b.get(T + f"{eid}/", **self.with_env(self.env_b.id))
        self.assertEqual(own.status_code, 404)

    def test_foreign_group_is_rejected(self):
        from academics.models import Grade as G
        fg = G.objects.create(environment=self.env_b, name="x", fee_amount=1)
        fgr = Group.objects.create(environment=self.env_b, grade=fg, name="y")
        r = self.t("post", "", {"title": "x", "questions": questions(1), "group_ids": [fgr.id]})
        self.assertEqual(r.status_code, 400)

    def test_editing_is_frozen_once_someone_started(self):
        eid = self.make_exam()
        self.s("post", f"{eid}/start/")
        r = self.t("put", f"{eid}/", {"title": "جديد", "questions": questions(1)})
        self.assertEqual(r.status_code, 400)

    def test_results_list_everyone_in_the_audience(self):
        eid = self.make_exam()
        self.answer_all(eid)
        self.s("post", f"{eid}/submit/")
        body = self.t("get", f"{eid}/results/").json()
        self.assertEqual(body["total"], 1)  # only G1 was targeted
        self.assertEqual(body["results"][0]["status"], "finished")
        self.assertEqual(body["results"][0]["percent"], 100.0)


class StudentSideTests(ExamBase):
    def test_audience_is_enforced(self):
        eid = self.make_exam()
        self.assertEqual(self.s("get", "").json()["results"][0]["id"], eid)
        self.assertEqual(self.s("get", "", client=self.peer).json()["results"], [])
        self.assertEqual(self.s("post", f"{eid}/start/", client=self.peer).status_code, 404)

    def test_questions_never_reveal_the_answer_key(self):
        eid = self.make_exam()
        self.s("post", f"{eid}/start/")
        q = self.s("get", f"{eid}/question/0/")
        self.assertNotIn("is_correct", q.content.decode())
        self.assertIn("no-store", q["Cache-Control"])

    def test_forward_only_blocks_going_back_and_jumping_ahead(self):
        eid = self.make_exam()
        self.s("post", f"{eid}/start/")
        q0 = self.s("get", f"{eid}/question/0/").json()
        self.assertEqual(self.s("get", f"{eid}/question/1/").status_code, 400)  # can't peek ahead
        self.s("post", f"{eid}/answer/", {"question_id": q0["question_id"], "choice_id": q0["choices"][0]["id"]})
        self.assertEqual(self.s("get", f"{eid}/question/0/").status_code, 400)  # can't go back
        self.assertEqual(self.s("get", f"{eid}/question/1/").status_code, 200)

    def test_allow_back_lets_the_student_review(self):
        eid = self.make_exam(allow_back=True)
        self.s("post", f"{eid}/start/")
        q0 = self.s("get", f"{eid}/question/0/").json()
        self.s("post", f"{eid}/answer/", {"question_id": q0["question_id"], "choice_id": q0["choices"][0]["id"]})
        self.assertEqual(self.s("get", f"{eid}/question/0/").status_code, 200)

    def test_grading_and_single_attempt(self):
        eid = self.make_exam()
        self.answer_all(eid)
        r = self.s("post", f"{eid}/submit/").json()
        self.assertTrue(r["finished"])
        res = self.s("get", f"{eid}/result/").json()
        self.assertEqual((res["score"], res["max_score"], res["percent"]), (6.0, 6.0, 100.0))
        self.assertNotIn("review", res)  # teacher did not reveal answers
        again = self.s("post", f"{eid}/start/").json()
        self.assertTrue(again["finished"])  # no second go
        self.assertEqual(Attempt.objects.count(), 1)

    def test_wrong_answers_score_zero(self):
        eid = self.make_exam()
        self.answer_all(eid, correct=False)
        self.s("post", f"{eid}/submit/")
        self.assertEqual(self.s("get", f"{eid}/result/").json()["score"], 0.0)

    def test_server_clock_closes_the_attempt(self):
        eid = self.make_exam()
        self.s("post", f"{eid}/start/")
        Attempt.objects.update(deadline_at=timezone.now() - timedelta(seconds=1))
        r = self.s("get", f"{eid}/question/0/")
        self.assertEqual(r.status_code, 400)
        self.assertEqual(Attempt.objects.get().end_reason, "time")

    def test_violations_close_the_attempt_at_the_limit(self):
        eid = self.make_exam(max_violations=2)
        self.s("post", f"{eid}/start/")
        a = Attempt.objects.get()
        # space the log entries apart so de-duplication does not merge them
        self.s("post", f"{eid}/violation/", {"type": "blur"})
        a.refresh_from_db(); log = a.violation_log; log[0]["at"] = (timezone.now() - timedelta(seconds=30)).isoformat()
        a.violation_log = log; a.save()
        st = self.s("post", f"{eid}/violation/", {"type": "blur"}).json()
        self.assertTrue(st["finished"])
        self.assertEqual(st["end_reason"], "violations")

    def test_unknown_violation_types_and_dupes_are_ignored(self):
        eid = self.make_exam()
        self.s("post", f"{eid}/start/")
        self.s("post", f"{eid}/violation/", {"type": "nonsense"})
        self.s("post", f"{eid}/violation/", {"type": "hidden"})
        self.s("post", f"{eid}/violation/", {"type": "hidden"})  # same event twice within 3 s
        self.assertEqual(Attempt.objects.get().violations, 1)

    def test_cannot_start_before_open_or_after_close(self):
        soon = (timezone.now() + timedelta(hours=1)).isoformat()
        e1 = self.make_exam(opens_at=soon)
        self.assertEqual(self.s("post", f"{e1}/start/").status_code, 400)
        past_open = (timezone.now() - timedelta(hours=2)).isoformat()
        past_close = (timezone.now() - timedelta(hours=1)).isoformat()
        e2 = self.make_exam(opens_at=past_open, closes_at=past_close)
        self.assertEqual(self.s("post", f"{e2}/start/").status_code, 400)

    def test_review_only_after_finishing_and_only_when_revealed(self):
        eid = self.make_exam(reveal_answers=True)
        self.s("post", f"{eid}/start/")
        self.assertEqual(self.s("get", f"{eid}/result/").status_code, 400)
        self.answer_all(eid)
        self.s("post", f"{eid}/submit/")
        self.assertIn("review", self.s("get", f"{eid}/result/").json())

    def test_question_order_is_stored_per_student(self):
        eid = self.make_exam(group_ids=[self.g1.id, self.g2.id])
        a1 = self.s("post", f"{eid}/start/").json()["attempt_id"]
        self.assertEqual(sorted(Attempt.objects.get(pk=a1).question_order),
                         sorted(Exam.objects.get(pk=eid).questions.values_list("pk", flat=True)))


class ViolationWarningTests(ExamBase):
    def test_one_leaving_is_one_warning_even_if_the_browser_fires_several_events(self):
        eid = self.make_exam()
        self.s("post", f"{eid}/start/")
        first = self.s("post", f"{eid}/violation/", {"type": "blur"}).json()
        self.assertTrue(first["counted"])
        self.assertEqual((first["violations"], first["warnings_left"], first["last_violation"]), (1, 2, "blur"))
        for kind in ("hidden", "fullscreen_exit"):  # the same alt-tab, reported again a moment later
            again = self.s("post", f"{eid}/violation/", {"type": kind}).json()
            self.assertFalse(again["counted"])
            self.assertEqual(again["violations"], 1)
        self.assertEqual(Attempt.objects.get().violations, 1)

    def test_different_kinds_each_count(self):
        eid = self.make_exam()
        self.s("post", f"{eid}/start/")
        self.s("post", f"{eid}/violation/", {"type": "blur"})
        r = self.s("post", f"{eid}/violation/", {"type": "copy"}).json()
        self.assertTrue(r["counted"])
        self.assertEqual(r["violations"], 2)


class RetakeTests(ExamBase):
    """The teacher re-opens an exam for one student; the student sits it again; the BEST score counts."""

    def sit(self, eid, correct, retake=False):
        st = self.s("post", f"{eid}/start/", {"retake": True} if retake else {})
        self.assertEqual(st.status_code, 200, st.content)
        for i in range(st.json()["total"]):
            q = self.s("get", f"{eid}/question/{i}/").json()
            truth = Exam.objects.get(pk=eid).questions.get(pk=q["question_id"]).choices.get(is_correct=True).pk
            wrong = next(c["id"] for c in q["choices"] if c["id"] != truth)
            self.s("post", f"{eid}/answer/", {"question_id": q["question_id"], "choice_id": truth if correct else wrong})
        self.s("post", f"{eid}/submit/")

    def reopen(self, eid, enrollment=None):
        return self.t("post", f"{eid}/reopen/", {"enrollment_id": (enrollment or self.e1).pk})

    def row(self, eid):
        return self.t("get", f"{eid}/results/").json()["results"][0]

    def test_no_second_go_without_the_teacher(self):
        eid = self.make_exam()
        self.sit(eid, correct=False)
        r = self.s("post", f"{eid}/start/", {"retake": True})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "no_retake")
        row = self.s("get", "").json()["results"][0]
        self.assertFalse(row["can_retake"])

    def test_reopen_then_retake_and_the_best_score_counts(self):
        eid = self.make_exam()
        self.sit(eid, correct=False)  # 0 / 6
        r = self.reopen(eid)
        self.assertEqual(r.status_code, 200, r.content)
        listed = self.s("get", "").json()["results"][0]
        self.assertEqual((listed["state"], listed["can_retake"]), ("finished", True))
        self.sit(eid, correct=True, retake=True)  # 6 / 6
        res = self.s("get", f"{eid}/result/").json()
        self.assertEqual((res["attempt_number"], res["percent"], res["best_percent"], res["is_best"]), (2, 100.0, 100.0, True))
        row = self.row(eid)
        self.assertEqual((row["percent"], row["best_attempt"], row["attempt_count"]), (100.0, 2, 2))
        self.assertEqual([a["percent"] for a in row["attempts"]], [0, 100.0])
        self.assertFalse(row["reopened"])  # the grant was used up
        self.assertEqual(Attempt.objects.count(), 2)

    def test_a_worse_retake_never_lowers_the_score(self):
        eid = self.make_exam()
        self.sit(eid, correct=True)
        self.reopen(eid)
        self.sit(eid, correct=False, retake=True)
        res = self.s("get", f"{eid}/result/").json()
        self.assertEqual((res["percent"], res["best_percent"], res["is_best"]), (0, 100.0, False))
        listed = self.s("get", "").json()["results"][0]
        self.assertEqual(listed["percent"], 100.0)
        self.assertEqual(self.row(eid)["percent"], 100.0)

    def test_reopening_is_one_sitting_and_idempotent(self):
        eid = self.make_exam()
        self.sit(eid, correct=False)
        self.assertEqual(self.reopen(eid).status_code, 200)
        again = self.reopen(eid)
        self.assertTrue(again.json()["already"])
        self.assertEqual(AttemptGrant.objects.count(), 1)
        self.sit(eid, correct=True, retake=True)
        self.assertEqual(self.s("post", f"{eid}/start/", {"retake": True}).status_code, 400)  # used up

    def test_cannot_reopen_while_the_student_is_still_sitting(self):
        eid = self.make_exam()
        self.s("post", f"{eid}/start/")
        r = self.reopen(eid)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "in_progress")

    def test_reopen_after_the_exam_closed_for_someone_who_never_sat_it(self):
        eid = self.make_exam(opens_at=(timezone.now() - timedelta(hours=3)).isoformat(),
                             closes_at=(timezone.now() - timedelta(hours=1)).isoformat())
        self.assertEqual(self.s("post", f"{eid}/start/").status_code, 400)  # closed
        self.assertTrue(self.row(eid)["can_reopen"])
        self.assertEqual(self.reopen(eid).status_code, 200)
        st = self.s("post", f"{eid}/start/")
        self.assertEqual(st.status_code, 200, st.content)
        # the clock is the exam's duration from NOW, not clamped to the past closing time
        self.assertGreater(Attempt.objects.get().deadline_at, timezone.now() + timedelta(minutes=10))

    def test_an_open_exam_is_not_reopened_for_someone_who_has_not_started(self):
        eid = self.make_exam()
        r = self.reopen(eid)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "already_open")
        self.assertFalse(self.row(eid)["can_reopen"])

    def test_only_this_teachers_students_and_audience(self):
        eid = self.make_exam()
        self.sit(eid, correct=False)
        self.assertEqual(self.reopen(eid, self.e2).status_code, 400)  # G2 is not in the audience
        self.assertEqual(self.client_b.post(T + f"{eid}/reopen/", {"enrollment_id": self.e1.pk}, format="json",
                                            **self.with_env(self.env_b.id)).status_code, 404)
        self.assertEqual(self.t("post", f"{eid}/reopen/", {}).status_code, 400)

    def test_the_student_is_told_and_can_open_the_exam_from_the_notification(self):
        eid = self.make_exam()
        self.sit(eid, correct=False)
        self.reopen(eid)
        n = Notification.objects.filter(type="new_exam").order_by("-id").first()
        self.assertEqual((n.exam_id, n.title), (eid, "أُعيد فتح الامتحان لك"))
        rows = self.me.get("/api/v1/student/notifications/", **self.with_env(self.env_a.id)).json()["results"]
        self.assertEqual(rows[0]["target"], {"kind": "exam", "id": eid})
        self.assertEqual(rows[0]["type"], "new_exam")

    def test_answers_are_not_shown_while_a_retake_is_waiting(self):
        eid = self.make_exam(reveal_answers=True)
        self.sit(eid, correct=False)
        self.assertIn("review", self.s("get", f"{eid}/result/").json())
        self.reopen(eid)
        self.assertNotIn("review", self.s("get", f"{eid}/result/").json())

    def test_the_average_uses_the_best_sitting(self):
        eid = self.make_exam()
        self.sit(eid, correct=False)
        self.reopen(eid)
        self.sit(eid, correct=True, retake=True)
        self.assertEqual(self.t("get", f"{eid}/results/").json()["average_percent"], 100.0)


class ExamNotificationTests(ExamBase):
    def test_publishing_sends_an_exam_notification_not_a_video_one(self):
        eid = self.make_exam()
        n = Notification.objects.get(exam_id=eid)
        self.assertEqual((n.type, n.title), ("new_exam", "امتحان جديد"))
        self.assertEqual(n.student_path(), f"/learn/exams/{eid}")
        self.assertFalse(Notification.objects.filter(type="new_video").exists())

    def test_the_teacher_log_has_one_line_per_exam(self):
        self.make_exam(group_ids=[self.g1.id, self.g2.id])
        rows = self.t("get", "").json()  # sanity: the exam list itself still works
        self.assertEqual(len(rows["results"]), 1)
        log = self.client_a.get("/api/v1/notifications/?type=new_exam", **self.with_env(self.env_a.id)).json()
        results = log["results"] if isinstance(log, dict) else log
        self.assertEqual(len(results), 1)  # two students were notified, ONE line
        self.assertEqual(results[0]["exam"]["title"], "امتحان")
        self.assertEqual(results[0]["type_label"], "امتحان جديد")


class OldNotificationRelabelTests(ExamBase):
    def test_the_migration_fixes_rows_written_before_the_new_types_existed(self):
        import importlib

        from django.apps import apps

        from content.models import ContentItem

        mig = importlib.import_module("notifications.migrations.0006_exam_retakes")
        pdf = ContentItem.objects.create(environment=self.env_a, title="ملف", kind="pdf")
        common = dict(environment=self.env_a, recipient=self.me_user if hasattr(self, "me_user") else self.e1.student,
                      enrollment=self.e1)
        old_exam = Notification.objects.create(type="new_video", title="امتحان جديد", **common)
        old_pdf = Notification.objects.create(type="new_video", title="ملف جديد", content_item=pdf, **common)
        video = ContentItem.objects.create(environment=self.env_a, title="فيديو", kind="video")
        keep = Notification.objects.create(type="new_video", title="فيديو جديد", content_item=video, **common)
        mig.relabel_old_rows(apps, None)
        self.assertEqual(Notification.objects.get(pk=old_exam.pk).type, "new_exam")
        self.assertEqual(Notification.objects.get(pk=old_pdf.pk).type, "new_material")
        self.assertEqual(Notification.objects.get(pk=keep.pk).type, "new_video")


class ThrottleTests(ExamBase):
    """The autosave and the integrity-event endpoints are capped per student, so a script cannot flood them."""

    def test_violation_reports_are_rate_limited(self):
        eid = self.make_exam()
        self.s("post", f"{eid}/start/")
        cache.clear()
        rates = {"exam-event": "5/min", "exam-answer": "5/min"}
        with mock.patch.dict("rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES", rates):
            codes = [self.s("post", f"{eid}/violation/", {"type": "copy"}).status_code for _ in range(8)]
        self.assertIn(429, codes)
        self.assertEqual(codes[0], 200)
        cache.clear()

    def test_answers_are_rate_limited(self):
        eid = self.make_exam()
        self.s("post", f"{eid}/start/")
        q = self.s("get", f"{eid}/question/0/").json()
        cache.clear()
        rates = {"exam-event": "5/min", "exam-answer": "5/min"}
        with mock.patch.dict("rest_framework.throttling.SimpleRateThrottle.THROTTLE_RATES", rates):
            codes = [self.s("post", f"{eid}/answer/", {"question_id": q["question_id"],
                                                        "choice_id": q["choices"][0]["id"]}).status_code
                     for _ in range(8)]
        self.assertIn(429, codes)
        cache.clear()
