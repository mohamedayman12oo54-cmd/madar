"""One session per group, planned in a single call: a group, several groups,
or a whole grade - never a group the teacher does not own."""
import datetime as dt

from django.utils import timezone

from academics.models import Grade, Group

from .models import SessionInstance
from .tests import Base

WHEN = (timezone.now() + dt.timedelta(days=3)).replace(microsecond=0)


class BulkSessionTests(Base):
    def setUp(self):
        super().setUp()
        self.g3 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G3")
        self.grade2 = Grade.objects.create(environment=self.env_a, name="ثاني", fee_amount=100)
        self.h1 = Group.objects.create(environment=self.env_a, grade=self.grade2, name="H1")

    def bulk(self, body, **kw):
        return self.call("post", "sessions/bulk/", {"scheduled_at": WHEN.isoformat(), **body}, **kw)

    def groups_of(self):
        return set(SessionInstance.objects.filter(scheduled_at=WHEN).values_list("group__name", flat=True))

    def test_whole_grade_makes_one_session_per_group_of_that_grade_only(self):
        r = self.bulk({"grade_id": self.grade.id})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.data["created"], 3)
        self.assertEqual(self.groups_of(), {"G1", "G2", "G3"})  # not H1 (other grade)

    def test_some_groups_of_a_grade(self):
        r = self.bulk({"grade_id": self.grade.id, "group_ids": [self.g1.id, self.g3.id]})
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.groups_of(), {"G1", "G3"})

    def test_a_group_outside_the_chosen_grade_is_refused_and_nothing_is_created(self):
        r = self.bulk({"grade_id": self.grade.id, "group_ids": [self.g1.id, self.h1.id]})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.groups_of(), set())

    def test_groups_alone_without_a_grade(self):
        r = self.bulk({"group_ids": [self.h1.id]})
        self.assertEqual(r.status_code, 201)
        self.assertEqual(self.groups_of(), {"H1"})

    def test_repeating_the_same_request_never_doubles_a_lesson(self):
        self.bulk({"grade_id": self.grade.id})
        again = self.bulk({"grade_id": self.grade.id})
        self.assertEqual(again.data["created"], 0)
        self.assertEqual(sorted(again.data["skipped"]), ["G1", "G2", "G3"])
        self.assertEqual(SessionInstance.objects.filter(scheduled_at=WHEN).count(), 3)

    def test_needs_a_target(self):
        self.assertEqual(self.bulk({}).status_code, 400)

    def test_another_teacher_cannot_plan_sessions_on_my_groups(self):
        r = self.bulk({"group_ids": [self.g1.id]}, client=self.client_b, env=self.env_b)
        self.assertEqual(r.status_code, 400)
        r = self.bulk({"grade_id": self.grade.id}, client=self.client_b, env=self.env_b)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.groups_of(), set())

    def test_list_can_be_filtered_by_grade(self):
        self.bulk({"group_ids": [self.g1.id, self.h1.id]})
        r = self.call("get", f"sessions/?grade_id={self.grade2.id}")
        rows = r.data["results"] if isinstance(r.data, dict) else r.data
        self.assertEqual([x["group"]["name"] for x in rows], ["H1"])
