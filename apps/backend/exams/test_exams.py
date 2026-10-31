"""Exams: authoring, sending, taking and integrity.

What these tests pin down (and why): the paper a student receives NEVER carries the answer key; the
clock is the server's; one attempt per student; grading is server-side and idempotent; grade + group
narrow the audience; a teacher can only touch their own exams; integrity signals are counted once per
departure and end the attempt at the teacher's limit; the correct answers are shown only after the
window closes and only if the teacher allowed it."""
import json
from datetime import timedelta
from unittest import mock

from django.utils import timezone
from rest_framework.test import APIClient

from academics.models import Enrollment, Grade, Group
from environments.tenancy_testing import PASSWORD, TenantTestCase
from notifications.models import Notification

from .models import Attempt, Choice, Exam, IntegrityEvent, Question

API = "/api/v1/exams/"


def paper(n=3):
    """n questions, 3 choices each, the FIRST choice correct, 1 point each (2 for the last)."""
    return [{
        "text": f"سؤال {i + 1}",
        "points": 2 if i == n - 1 else 1,
        "choices": [{"text": "الصحيحة", "is_correct": True}, {"text": "خطأ ١", "is_correct": False},
                    {"text": "خطأ ٢", "is_correct": False}],
    } for i in range(n)]


class _Base(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.t0 = timezone.now()
        self.clock = self.t0
        patcher = mock.patch("exams.services.now", side_effect=lambda: self.clock)
        patcher.start()
        self.addCleanup(patcher.stop)

        self.grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.other_grade = Grade.objects.create(environment=self.env_a, name="ثاني")
        self.g1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.g2 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        self.s1, self.e1 = self._student("201555900001", self.grade, [self.g1])
        self.s2, self.e2 = self._student("201555900002", self.grade, [self.g2])
        self.s3, self.e3 = self._student("201555900003", self.other_grade, [])
        self.c1, self.c2, self.c3 = (self._login(s) for s in (self.s1, self.s2, self.s3))

    def _student(self, phone, grade, groups):
        s = self.make_student_in(self.env_a, phone, "طالب " + phone[-2:])
        s.set_password(PASSWORD)
        s.is_active = True
        s.is_verified = True
        s.save()
        enr = Enrollment.objects.create(environment=self.env_a, student=s, grade=grade, parent_phone="201111000001")
        enr.groups.set(groups)
        return s, enr

    def _login(self, user):
        c = APIClient()
        tok = c.post("/api/v1/auth/student/login/", {"phone": user.phone, "password": PASSWORD}).data["access"]
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        return c

    # teacher helpers
    def body(self, **extra):
        b = {"title": "امتحان الباب الأول", "duration_minutes": 30, "closes_at": (self.t0 + timedelta(days=2)).isoformat(),
             "grade_ids": [self.grade.id], "questions": paper(), **extra}
        return b

    def create(self, client=None, env=None, **extra):
        return (client or self.client_a).post(API, self.body(**extra), format="json",
                                              **self.with_env((env or self.env_a).id))

    def make(self, publish=True, **extra):
        r = self.create(**extra)
        self.assertEqual(r.status_code, 201, r.content)
        exam = Exam.objects.get(pk=r.json()["id"])
        if publish:
            p = self.client_a.post(f"{API}{exam.id}/publish/", **self.with_env(self.env_a.id))
            self.assertEqual(p.status_code, 200, p.content)
            exam.refresh_from_db()
        return exam

    def tget(self, url, **kw):
        return self.client_a.get(API + url, **self.with_env(self.env_a.id), **kw)

    def tpost(self, url, data=None, **kw):
        return self.client_a.post(API + url, data, format="json", **self.with_env(self.env_a.id), **kw)

    # student helpers
    def sget(self, client, url):
        return client.get(f"{API}student/{url}", **self.with_env(self.env_a.id))

    def spost(self, client, url, data=None):
        return client.post(f"{API}student/{url}", data, format="json", **self.with_env(self.env_a.id))

    def sput(self, client, url, data):
        return client.put(f"{API}student/{url}", data, format="json", **self.with_env(self.env_a.id))

    def start(self, exam, client=None):
        r = self.spost(client or self.c1, f"{exam.id}/start/")
        self.assertIn(r.status_code, (200, 201), r.content)
        return r.json()

    def right(self, exam, qid):
        return Choice.objects.get(question_id=qid, is_correct=True).id

    def wrong(self, exam, qid):
        return Choice.objects.filter(question_id=qid, is_correct=False).first().id


# --------------------------------------------------------------------------------------- authoring
class AuthoringTests(_Base):
    def test_teacher_creates_an_exam_with_questions(self):
        r = self.create()
        self.assertEqual(r.status_code, 201, r.content)
        d = r.json()
        self.assertEqual(d["question_count"], 3)
        self.assertEqual(d["total_points"], 4)
        self.assertEqual([c["is_correct"] for c in d["questions"][0]["choices"]], [True, False, False])
        self.assertFalse(d["published"])

    def test_a_question_needs_exactly_one_correct_choice(self):
        none_correct = paper(1)
        none_correct[0]["choices"][0]["is_correct"] = False
        two_correct = paper(1)
        two_correct[0]["choices"][1]["is_correct"] = True
        for bad in (none_correct, two_correct):
            self.assertEqual(self.create(questions=bad).status_code, 400)

    def test_choice_count_blank_text_and_duplicates_are_refused(self):
        one = paper(1)
        one[0]["choices"] = one[0]["choices"][:1]
        seven = paper(1)
        seven[0]["choices"] = [{"text": f"c{i}", "is_correct": i == 0} for i in range(7)]
        blank = paper(1)
        blank[0]["choices"][1]["text"] = "   "
        dup = paper(1)
        dup[0]["choices"][2]["text"] = "خطأ ١"
        no_text = paper(1)
        no_text[0]["text"] = ""
        for bad in (one, seven, blank, dup, no_text):
            self.assertEqual(self.create(questions=bad).status_code, 400, bad)

    def test_window_must_be_sensible(self):
        past = (self.t0 - timedelta(hours=1)).isoformat()
        self.assertEqual(self.create(closes_at=past).status_code, 400)
        opens = (self.t0 + timedelta(days=3)).isoformat()
        self.assertEqual(self.create(opens_at=opens).status_code, 400)  # closes (2d) before it opens (3d)
        self.assertEqual(self.create(duration_minutes=0).status_code, 400)
        self.assertEqual(self.create(duration_minutes=601).status_code, 400)

    def test_targets_must_belong_to_the_teachers_own_environment(self):
        foreign = Grade.objects.create(environment=self.env_b, name="غريب")
        self.assertEqual(self.create(grade_ids=[foreign.id]).status_code, 400)

    def test_teacher_b_cannot_read_edit_publish_or_delete_teacher_a_exam(self):
        exam = self.make(publish=False)
        for method, url in (("get", f"{API}{exam.id}/"), ("patch", f"{API}{exam.id}/"),
                            ("delete", f"{API}{exam.id}/"), ("post", f"{API}{exam.id}/publish/"),
                            ("get", f"{API}{exam.id}/results/")):
            r = getattr(self.client_b, method)(url, **self.with_env(self.env_b.id))
            self.assertEqual(r.status_code, 404, (method, url))
        # naming A's environment is refused outright
        self.assert_cross_tenant_denied("get", API)
        self.assertEqual(self.client_b.get(API, **self.with_env(self.env_b.id)).json()["results"], [])

    def test_students_cannot_use_the_teacher_endpoints(self):
        exam = self.make(publish=False)
        for r in (self.c1.get(API, **self.with_env(self.env_a.id)),
                  self.c1.post(API, self.body(), format="json", **self.with_env(self.env_a.id)),
                  self.c1.get(f"{API}{exam.id}/results/", **self.with_env(self.env_a.id))):
            self.assertIn(r.status_code, (401, 403))

    def test_draft_can_be_fully_edited_and_questions_replaced(self):
        exam = self.make(publish=False)
        r = self.client_a.patch(f"{API}{exam.id}/", {"title": "جديد", "questions": paper(5)}, format="json",
                                **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["question_count"], 5)
        self.assertEqual(Question.objects.filter(exam=exam).count(), 5)

    def test_publish_needs_targets_and_questions_and_happens_once(self):
        no_target = self.create(grade_ids=[]).json()["id"]
        r = self.tpost(f"{no_target}/publish/")
        self.assertEqual(r.status_code, 400)
        empty = self.create(questions=[]).json()["id"]
        self.assertEqual(self.tpost(f"{empty}/publish/").status_code, 400)
        exam = self.make()
        again = self.tpost(f"{exam.id}/publish/")
        self.assertEqual(again.status_code, 409)
        self.assertEqual(again.json()["code"], "already_published")

    def test_publish_notifies_exactly_the_audience_once(self):
        exam = self.make(publish=False, grade_ids=[self.grade.id], group_ids=[self.g1.id])
        r = self.tpost(f"{exam.id}/publish/")
        self.assertEqual(r.json()["notified"], 1)  # grade AND group narrow: only s1
        n = Notification.objects.filter(title="امتحان جديد")
        self.assertEqual(list(n.values_list("recipient_id", flat=True)), [self.s1.id])

    def test_after_publishing_only_safe_fields_can_change(self):
        exam = self.make()
        url = f"{API}{exam.id}/"
        env = self.with_env(self.env_a.id)
        self.assertEqual(self.client_a.patch(url, {"questions": paper(1)}, format="json", **env).status_code, 409)
        self.assertEqual(self.client_a.patch(url, {"duration_minutes": 5}, format="json", **env).status_code, 409)
        self.assertEqual(self.client_a.patch(url, {"title": "اسم جديد"}, format="json", **env).status_code, 200)
        later = (exam.closes_at + timedelta(days=1)).isoformat()
        self.assertEqual(self.client_a.patch(url, {"closes_at": later}, format="json", **env).status_code, 200)
        sooner = (exam.closes_at - timedelta(days=1)).isoformat()
        self.assertEqual(self.client_a.patch(url, {"closes_at": sooner}, format="json", **env).status_code, 400)

    def test_cannot_delete_an_exam_students_have_started(self):
        exam = self.make()
        self.start(exam)
        r = self.client_a.delete(f"{API}{exam.id}/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.json()["code"], "has_attempts")
        other = self.make(publish=False)
        self.assertEqual(self.client_a.delete(f"{API}{other.id}/", **self.with_env(self.env_a.id)).status_code, 204)


# --------------------------------------------------------------------------------------- taking
class TakingTests(_Base):
    def test_only_targeted_students_see_and_start_the_exam(self):
        exam = self.make()
        self.assertEqual([x["id"] for x in self.sget(self.c1, "").json()["results"]], [exam.id])
        self.assertEqual(self.sget(self.c3, "").json()["results"], [])  # other grade
        self.assertEqual(self.sget(self.c3, f"{exam.id}/").status_code, 404)
        self.assertEqual(self.spost(self.c3, f"{exam.id}/start/").status_code, 404)

    def test_an_unpublished_exam_is_invisible(self):
        exam = self.make(publish=False)
        self.assertEqual(self.sget(self.c1, "").json()["results"], [])
        self.assertEqual(self.spost(self.c1, f"{exam.id}/start/").status_code, 404)

    def test_the_paper_never_contains_the_answer_key(self):
        exam = self.make(reveal_answers=True)
        payload = self.start(exam)
        text = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("is_correct", text)
        self.assertNotIn("correct", text)
        self.assertEqual(len(payload["questions"]), 3)
        for q in payload["questions"]:
            self.assertEqual(set(q), {"id", "text", "points", "choices", "chosen"})
            for c in q["choices"]:
                self.assertEqual(set(c), {"id", "text"})
        # nor before it: the exam info and list carry no questions at all
        self.assertNotIn("questions", self.sget(self.c1, f"{exam.id}/").json())

    def test_start_is_idempotent_and_the_paper_is_stable(self):
        exam = self.make()
        first = self.start(exam)
        second = self.start(exam)
        self.assertEqual(first["attempt"]["id"], second["attempt"]["id"])
        self.assertEqual(first["attempt"]["deadline_at"], second["attempt"]["deadline_at"])
        self.assertEqual([q["id"] for q in first["questions"]], [q["id"] for q in second["questions"]])
        self.assertEqual(Attempt.objects.filter(exam=exam).count(), 1)
        a = Attempt.objects.get(exam=exam)
        self.assertEqual(sorted(a.question_order), sorted(exam.questions.values_list("id", flat=True)))

    def test_not_open_yet_and_already_closed(self):
        exam = self.make(opens_at=(self.t0 + timedelta(hours=1)).isoformat())
        r = self.spost(self.c1, f"{exam.id}/start/")
        self.assertEqual((r.status_code, r.json()["code"]), (403, "exam_not_open"))
        self.assertEqual(self.sget(self.c1, "").json()["results"][0]["status"], "upcoming")
        self.clock = exam.closes_at + timedelta(seconds=1)
        r = self.spost(self.c1, f"{exam.id}/start/")
        self.assertEqual((r.status_code, r.json()["code"]), (403, "exam_closed"))
        self.assertEqual(self.sget(self.c1, "").json()["results"][0]["status"], "missed")

    def test_deadline_is_the_duration_but_never_past_the_closing_time(self):
        exam = self.make(duration_minutes=30)
        self.assertEqual(self.start(exam)["attempt"]["deadline_at"][:19],
                         (self.t0 + timedelta(minutes=30)).isoformat()[:19])
        exam2 = self.make(duration_minutes=120, closes_at=(self.t0 + timedelta(minutes=20)).isoformat())
        a = self.start(exam2, self.c2 if False else self.c1)
        self.assertEqual(a["attempt"]["deadline_at"][:19], (self.t0 + timedelta(minutes=20)).isoformat()[:19])

    def test_answers_are_saved_and_validated(self):
        exam = self.make()
        paper_ = self.start(exam)["questions"]
        q = paper_[0]
        good = q["choices"][0]["id"]
        self.assertEqual(self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": good}).status_code, 200)
        resumed = self.start(exam)["questions"]
        self.assertEqual(next(x for x in resumed if x["id"] == q["id"])["chosen"], good)
        # a choice that belongs to ANOTHER question is refused
        other_choice = paper_[1]["choices"][0]["id"]
        r = self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": other_choice})
        self.assertEqual((r.status_code, r.json()["code"]), (400, "bad_choice"))
        # a question that is not in this exam is refused
        self.assertEqual(self.sput(self.c1, f"{exam.id}/answer/", {"question_id": 999999, "choice_id": good}).status_code, 400)
        # null clears the answer
        self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": None})
        self.assertIsNone(next(x for x in self.start(exam)["questions"] if x["id"] == q["id"])["chosen"])

    def test_grading_is_server_side_weighted_and_idempotent(self):
        exam = self.make()
        qs = self.start(exam)["questions"]
        by_text = {q["text"]: q for q in qs}
        for text in ("سؤال 1", "سؤال 3"):  # right on 1 (1pt) and 3 (2pt)
            q = by_text[text]
            self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": self.right(exam, q["id"])})
        q2 = by_text["سؤال 2"]
        self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q2["id"], "choice_id": self.wrong(exam, q2["id"])})
        r = self.spost(self.c1, f"{exam.id}/submit/")
        self.assertEqual((r.json()["score"], r.json()["max_score"]), (3, 4))
        again = self.spost(self.c1, f"{exam.id}/submit/")
        self.assertEqual(again.status_code, 200)
        self.assertEqual((again.json()["score"], again.json()["max_score"]), (3, 4))
        a = Attempt.objects.get()
        self.assertEqual(a.submit_reason, "manual")

    def test_nothing_can_be_saved_after_submitting_and_it_cannot_be_retaken(self):
        exam = self.make()
        q = self.start(exam)["questions"][0]
        self.spost(self.c1, f"{exam.id}/submit/")
        r = self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": q["choices"][0]["id"]})
        self.assertEqual((r.status_code, r.json()["code"]), (409, "attempt_finished"))
        again = self.spost(self.c1, f"{exam.id}/start/")
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["questions"], [])  # no paper is handed out again
        self.assertEqual(Attempt.objects.count(), 1)

    def test_running_out_of_time_grades_what_was_saved(self):
        exam = self.make(duration_minutes=10)
        q = self.start(exam)["questions"][0]
        self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": self.right(exam, q["id"])})
        self.clock = self.t0 + timedelta(minutes=10, seconds=1)
        late = self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": self.wrong(exam, q["id"])})
        self.assertEqual((late.status_code, late.json()["code"]), (409, "attempt_finished"))
        a = Attempt.objects.get()
        self.assertEqual((a.submit_reason, a.score), ("time", Question.objects.get(pk=q["id"]).points))
        self.assertLessEqual(a.submitted_at, a.deadline_at)

    def test_a_student_who_walked_away_is_settled_when_the_teacher_looks(self):
        exam = self.make(duration_minutes=10)
        self.start(exam)
        self.clock = self.t0 + timedelta(minutes=11)
        rows = self.tget(f"{exam.id}/results/").json()["results"]
        mine = next(r for r in rows if r["enrollment_id"] == self.e1.id)
        self.assertEqual((mine["status"], mine["submit_reason"]), ("submitted", "time"))

    def test_students_cannot_reach_each_others_attempts(self):
        exam = self.make()
        self.start(exam, self.c1)
        # s2 is targeted too (same grade), has not started: their own calls never see s1's data
        self.assertEqual(self.sput(self.c2, f"{exam.id}/answer/", {"question_id": 1, "choice_id": 1}).status_code, 404)
        self.assertEqual(self.sget(self.c2, f"{exam.id}/result/").status_code, 404)


# --------------------------------------------------------------------------------------- results
class ResultReleaseTests(_Base):
    def finish(self, exam, client=None):
        self.start(exam, client)
        return self.spost(client or self.c1, f"{exam.id}/submit/").json()

    def test_immediate_release_shows_the_score_at_once_but_no_review_before_close(self):
        exam = self.make(reveal_answers=True)
        out = self.finish(exam)
        self.assertEqual(out["score"], 0)
        self.assertNotIn("review", self.sget(self.c1, f"{exam.id}/result/").json())  # window still open

    def test_review_appears_after_close_only_when_the_teacher_allows_it(self):
        allowed = self.make(reveal_answers=True)
        denied = self.make(reveal_answers=False)
        self.finish(allowed)
        self.finish(denied)
        self.clock = self.t0 + timedelta(days=3)
        r = self.sget(self.c1, f"{allowed.id}/result/").json()
        self.assertEqual(len(r["review"]), 3)
        self.assertTrue(all(q["correct_choice_id"] for q in r["review"]))
        self.assertNotIn("review", self.sget(self.c1, f"{denied.id}/result/").json())

    def test_after_close_release_hides_the_score_until_the_window_ends(self):
        exam = self.make(results_release="after_close")
        out = self.finish(exam)
        self.assertEqual((out["score"], out["results_pending"]), (None, True))
        listed = self.sget(self.c1, "").json()["results"][0]
        self.assertEqual((listed["score"], listed["results_pending"]), (None, True))
        self.clock = self.t0 + timedelta(days=3)
        self.assertIsNotNone(self.sget(self.c1, f"{exam.id}/result/").json()["score"])

    def test_result_before_submitting_is_refused(self):
        exam = self.make()
        self.start(exam)
        r = self.sget(self.c1, f"{exam.id}/result/")
        self.assertEqual((r.status_code, r.json()["code"]), (409, "not_submitted"))


# --------------------------------------------------------------------------------------- integrity
class IntegrityTests(_Base):
    def event(self, exam, kind, client=None):
        return self.spost(client or self.c1, f"{exam.id}/events/", {"kind": kind})

    def test_counted_events_raise_the_violation_counter(self):
        exam = self.make(max_violations=5)
        self.start(exam)
        r = self.event(exam, "tab_hidden").json()
        self.assertEqual((r["counted"], r["violations"], r["submitted"]), (True, 1, False))

    def test_blocked_actions_are_logged_but_do_not_count(self):
        exam = self.make()
        self.start(exam)
        for kind in ("copy_attempt", "paste_attempt", "context_menu", "devtools_key", "resumed"):
            r = self.event(exam, kind).json()
            self.assertEqual((r["counted"], r["violations"]), (False, 0), kind)
        self.assertEqual(IntegrityEvent.objects.count(), 5)

    def test_one_departure_that_raises_several_signals_counts_once(self):
        exam = self.make(max_violations=5)
        self.start(exam)
        self.event(exam, "fullscreen_exit")
        self.clock += timedelta(milliseconds=400)
        self.event(exam, "window_blur")
        self.clock += timedelta(milliseconds=400)
        self.event(exam, "tab_hidden")
        self.assertEqual(Attempt.objects.get().violations, 1)
        self.assertEqual(IntegrityEvent.objects.count(), 3)  # all three are still on the record
        self.clock += timedelta(seconds=10)  # a second, separate departure
        self.event(exam, "tab_hidden")
        self.assertEqual(Attempt.objects.get().violations, 2)

    def test_reaching_the_limit_submits_the_attempt_and_grades_it(self):
        exam = self.make(max_violations=2)
        q = self.start(exam)["questions"][0]
        self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": self.right(exam, q["id"])})
        self.event(exam, "tab_hidden")
        self.clock += timedelta(seconds=10)
        r = self.event(exam, "fullscreen_exit").json()
        self.assertTrue(r["submitted"])
        self.assertEqual(r["submit_reason"], "violations")
        a = Attempt.objects.get()
        self.assertEqual(a.submit_reason, "violations")
        self.assertGreaterEqual(a.score, 1)
        # and nothing more is accepted
        late = self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": None})
        self.assertEqual(late.status_code, 409)

    def test_unknown_event_kinds_are_refused(self):
        exam = self.make()
        self.start(exam)
        self.assertEqual(self.event(exam, "made_up").status_code, 400)

    def test_events_before_starting_have_no_attempt(self):
        exam = self.make()
        self.assertEqual(self.event(exam, "tab_hidden").status_code, 404)

    def test_the_event_log_is_capped(self):
        exam = self.make(max_violations=10)
        self.start(exam)
        a = Attempt.objects.get()
        IntegrityEvent.objects.bulk_create(
            [IntegrityEvent(attempt=a, kind="copy_attempt", at=self.t0) for _ in range(IntegrityEvent.MAX_PER_ATTEMPT)])
        self.event(exam, "copy_attempt")
        self.assertEqual(IntegrityEvent.objects.filter(attempt=a).count(), IntegrityEvent.MAX_PER_ATTEMPT)


# --------------------------------------------------------------------------------------- teacher reads
class TeacherResultsTests(_Base):
    def test_results_list_everyone_in_the_audience_with_a_summary(self):
        exam = self.make()  # whole grade: s1 and s2
        q = self.start(exam, self.c1)["questions"][0]
        self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": self.right(exam, q["id"])})
        self.spost(self.c1, f"{exam.id}/submit/")
        self.start(exam, self.c2)  # in progress
        self.clock += timedelta(seconds=10)
        self.spost(self.c2, f"{exam.id}/events/", {"kind": "tab_hidden"})
        d = self.tget(f"{exam.id}/results/").json()
        by = {r["enrollment_id"]: r for r in d["results"]}
        self.assertEqual(set(by), {self.e1.id, self.e2.id})  # not s3 (other grade)
        self.assertEqual(by[self.e1.id]["status"], "submitted")
        self.assertEqual(by[self.e2.id]["status"], "in_progress")
        self.assertEqual(by[self.e2.id]["violations"], 1)
        self.assertEqual(d["summary"]["audience"], 2)
        self.assertEqual(d["summary"]["submitted"], 1)
        self.assertEqual(d["summary"]["flagged"], 1)

    def test_not_started_students_are_listed(self):
        exam = self.make()
        d = self.tget(f"{exam.id}/results/").json()
        self.assertEqual({r["status"] for r in d["results"]}, {"not_started"})

    def test_results_of_a_draft_are_refused(self):
        exam = self.make(publish=False)
        self.assertEqual(self.tget(f"{exam.id}/results/").status_code, 409)

    def test_attempt_detail_has_answers_key_and_the_integrity_log(self):
        exam = self.make(max_violations=9)
        q = self.start(exam)["questions"][0]
        self.sput(self.c1, f"{exam.id}/answer/", {"question_id": q["id"], "choice_id": self.wrong(exam, q["id"])})
        self.spost(self.c1, f"{exam.id}/events/", {"kind": "copy_attempt"})
        self.spost(self.c1, f"{exam.id}/events/", {"kind": "tab_hidden"})
        aid = Attempt.objects.get().id
        d = self.tget(f"{exam.id}/attempts/{aid}/").json()
        self.assertEqual([e["kind"] for e in d["events"]], ["copy_attempt", "tab_hidden"])
        self.assertEqual([e["counted"] for e in d["events"]], [False, True])
        row = next(x for x in d["questions"] if x["id"] == q["id"])
        self.assertFalse(row["is_correct"])
        self.assertTrue(row["correct_choice_id"])

    def test_teacher_b_cannot_read_an_attempt_of_teacher_a(self):
        exam = self.make()
        self.start(exam)
        aid = Attempt.objects.get().id
        r = self.client_b.get(f"{API}{exam.id}/attempts/{aid}/", **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)

    def test_resetting_an_attempt_lets_the_student_start_again(self):
        exam = self.make()
        self.start(exam)
        self.spost(self.c1, f"{exam.id}/submit/")
        aid = Attempt.objects.get().id
        r = self.client_a.delete(f"{API}{exam.id}/attempts/{aid}/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 204)
        again = self.spost(self.c1, f"{exam.id}/start/")
        self.assertEqual(again.status_code, 201)
        self.assertEqual(len(again.json()["questions"]), 3)
