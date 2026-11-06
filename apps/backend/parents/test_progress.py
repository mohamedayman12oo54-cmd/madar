"""Guardian portal: video watching, AI-quiz results and the month-by-month trend."""
from datetime import timedelta

from django.utils import timezone

from academics.models import Enrollment
from content.models import ContentItem, VideoProgress
from evaluation.models import MonthlyRating
from scheduling.models import AttendanceRecord, SessionInstance
from studentarea.models import Quiz, QuizAttempt

from .progress import _months_back
from .test_followup import make_exam, sit
from .tests import OVERVIEW, _Base


def video(env, enrollment, title, *, kind="video", published=True):
    item = ContentItem.objects.create(environment=env, title=title, kind=kind,
                                      published_at=timezone.now() if published else None)
    item.target_enrollments.add(enrollment)
    return item


class _P(_Base):
    def data(self, key):
        r = self.portal().get(OVERVIEW)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()[key]


class VideoWatchingTests(_P):
    def test_counts_and_per_video_percent(self):
        a, b, c = (video(self.env_a, self.enr, t) for t in ("أ", "ب", "ج"))
        VideoProgress.objects.create(environment=self.env_a, item=a, enrollment=self.enr, percent=100, completed=True)
        VideoProgress.objects.create(environment=self.env_a, item=b, enrollment=self.enr, percent=40)
        d = self.data("videos")
        self.assertEqual((d["total"], d["completed"], d["started"]), (3, 1, 2))
        self.assertEqual({r["title"]: r["percent"] for r in d["recent"]}, {"أ": 100, "ب": 40, "ج": 0})

    def test_only_published_videos_for_this_child_and_never_a_playable_reference(self):
        video(self.env_a, self.enr, "مسودة", published=False)
        video(self.env_a, self.enr, "ملخص", kind="summary")
        other_user = self.make_student_in(self.env_a, "201555800020", "زميل")
        self.activate(other_user)
        other = Enrollment.objects.create(environment=self.env_a, student=other_user, grade=self.grade,
                                          student_name="زميل", parent_phone="201099000666")
        video(self.env_a, other, "للزميل")
        mine = video(self.env_a, self.enr, "لي")
        VideoProgress.objects.create(environment=self.env_a, item=mine, enrollment=other, percent=90)
        d = self.data("videos")
        self.assertEqual([r["title"] for r in d["recent"]], ["لي"])
        self.assertEqual(d["recent"][0]["percent"], 0, "a classmate's progress is not mine")
        self.assertEqual(set(d["recent"][0]), {"id", "title", "percent", "completed", "last_watched_at"})


class QuizTests(_P):
    def attempt(self, title, score, total, enrollment=None):
        q = Quiz.objects.create(environment=self.env_a, enrollment=enrollment or self.enr, content_title=title)
        return QuizAttempt.objects.create(environment=self.env_a, quiz=q, score=score, total=total, answers=[])

    def test_average_and_recent_list(self):
        self.attempt("درس 1", 4, 5)
        self.attempt("درس 2", 2, 5)
        d = self.data("quizzes")
        self.assertEqual((d["taken"], d["average_percent"]), (2, 60.0))
        self.assertEqual({r["title"]: r["percent"] for r in d["recent"]}, {"درس 1": 80.0, "درس 2": 40.0})

    def test_nothing_taken_and_other_children_are_excluded(self):
        other_user = self.make_student_in(self.env_a, "201555800021", "زميل")
        self.activate(other_user)
        other = Enrollment.objects.create(environment=self.env_a, student=other_user, grade=self.grade,
                                          student_name="زميل", parent_phone="201099000777")
        self.attempt("للزميل", 5, 5, other)
        self.assertEqual(self.data("quizzes"), {"taken": 0, "average_percent": None, "recent": []})


class TrendTests(_P):
    def test_there_are_six_months_oldest_first_ending_this_month(self):
        t = self.data("trend")
        self.assertEqual(len(t), 6)
        self.assertEqual(t[-1]["month"], timezone.localdate().strftime("%Y-%m"))
        self.assertEqual([r["month"] for r in t], sorted(r["month"] for r in t))
        self.assertTrue(all(r["attendance_percent"] is None and r["exam_percent"] is None and r["rating"] is None
                            for r in t))

    def test_attendance_exam_and_rating_land_in_their_month(self):
        this = _months_back(1)[0]
        last = _months_back(2)[0]
        for when, status in ((this + timedelta(days=1), "present"), (this + timedelta(days=2), "present"),
                             (this + timedelta(days=3), "absent"), (last + timedelta(days=1), "absent")):
            s = SessionInstance.objects.create(
                environment=self.env_a, group=self.group,
                scheduled_at=timezone.make_aware(timezone.datetime(when.year, when.month, when.day, 12)))
            AttendanceRecord.objects.create(environment=self.env_a, session=s, enrollment=self.enr, status=status)
        exam = make_exam(self.env_a, self.enr)
        sit(exam, self.enr, 1, 8)  # handed in now = this month
        MonthlyRating.objects.create(environment=self.env_a, enrollment=self.enr, month=last, value=4,
                                     published_at=timezone.now())
        MonthlyRating.objects.create(environment=self.env_a, enrollment=self.enr, month=this, value=2)  # draft
        t = {r["month"]: r for r in self.data("trend")}
        now_row, last_row = t[this.strftime("%Y-%m")], t[last.strftime("%Y-%m")]
        self.assertEqual(now_row["attendance_percent"], 66.7)
        self.assertEqual(now_row["exam_percent"], 80.0)
        self.assertIsNone(now_row["rating"], "an unpublished draft is the teacher's working note")
        self.assertEqual((last_row["attendance_percent"], last_row["rating"]), (0.0, 4))
