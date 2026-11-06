"""Guardian replies to the teacher, the teacher's unread badge, and the optional class ranking."""
from rest_framework.test import APIClient

from academics.models import Enrollment, Group

from .models import MAX_REPLIES_PER_MESSAGE, GuardianAlertSettings, GuardianMessage, GuardianReply
from .progress import MIN_RANKED
from .test_followup import SEND, make_exam, sit
from .tests import OVERVIEW, _Base


class _Conv(_Base):
    def send(self, enrollment=None, **over):
        body = {"enrollment_id": (enrollment or self.enr).id, "kind": "warning", "title": "تحذير", "body": "نص", **over}
        r = self.client_a.post(SEND, body, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 201, r.content)
        return r.json()["id"]

    def reply(self, pk, body="حاضر، سأتابعه", client=None):
        return (client or self.portal()).post(f"/api/v1/parent/messages/{pk}/reply/", {"body": body}, format="json")

    def teacher(self, method, path, data=None):
        return getattr(self.client_a, method)(SEND + path, data or {}, format="json", **self.with_env(self.env_a.id))

    def sibling(self, phone="201555800040", guardian="201099000901", name="زميل"):
        user = self.make_student_in(self.env_a, phone, name)
        self.activate(user)
        e = Enrollment.objects.create(environment=self.env_a, student=user, grade=self.grade,
                                      student_name=name, parent_phone=guardian)
        e.groups.set([self.group])
        return e


class GuardianReplyTests(_Conv):
    def test_a_reply_is_stored_trimmed_and_shown_to_both_sides(self):
        pk = self.send()
        r = self.reply(pk, "  حاضر، سأتابعه  ")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(r.json()["body"], "حاضر، سأتابعه")
        m = self.portal().get(OVERVIEW).json()["messages"][0]
        self.assertEqual([x["body"] for x in m["replies"]], ["حاضر، سأتابعه"])
        self.assertTrue(m["can_reply"])
        hist = self.teacher("get", "", {"enrollment": self.enr.id}).json()["results"][0]
        self.assertEqual([x["body"] for x in hist["replies"]], ["حاضر، سأتابعه"])

    def test_the_number_of_replies_per_message_is_capped(self):
        pk = self.send()
        for _ in range(MAX_REPLIES_PER_MESSAGE):
            self.assertEqual(self.reply(pk).status_code, 201)
        r = self.reply(pk)
        self.assertEqual(r.status_code, 400)
        self.assertEqual(r.json()["code"], "reply_limit")
        self.assertEqual(GuardianReply.objects.count(), MAX_REPLIES_PER_MESSAGE)
        self.assertFalse(self.portal().get(OVERVIEW).json()["messages"][0]["can_reply"])

    def test_blank_and_oversized_replies_are_refused(self):
        pk = self.send()
        for bad in ("", "   ", "س" * 501):
            self.assertEqual(self.reply(pk, bad).status_code, 400, bad[:5])
        self.assertEqual(GuardianReply.objects.count(), 0)

    def test_markup_is_stored_as_plain_text_never_interpreted(self):
        pk = self.send()
        evil = "<img src=x onerror=alert(1)>"
        self.assertEqual(self.reply(pk, evil).status_code, 201)
        self.assertEqual(GuardianReply.objects.get().body, evil)

    def test_a_guardian_cannot_reply_to_another_childs_message(self):
        other = self.sibling()
        pk = self.send(other)
        self.assertEqual(self.reply(pk).status_code, 404)
        self.assertEqual(GuardianReply.objects.count(), 0)

    def test_nobody_but_a_guardian_can_reply(self):
        pk = self.send()
        url = f"/api/v1/parent/messages/{pk}/reply/"
        self.assertEqual(APIClient().post(url, {"body": "x"}, format="json").status_code, 401)
        r = self.client_a.post(url, {"body": "x"}, format="json", **self.with_env(self.env_a.id))
        self.assertIn(r.status_code, (401, 403))

    def test_the_hourly_cap_is_per_child_not_shared_between_guardians(self):
        other = self.sibling()
        mine = [self.send() for _ in range(7)]
        theirs = self.send(other)
        statuses = []
        for i in range(21):  # 3 replies on each of 7 messages = 21 attempts; the cap is 20 an hour
            statuses.append(self.reply(mine[i // 3]).status_code)
        self.assertEqual(statuses[:20], [201] * 20)
        self.assertEqual(statuses[20], 429)
        self.assertEqual(self.reply(theirs, client=self.portal(other)).status_code, 201,
                         "another child's guardian is not throttled by mine")


class TeacherInboxTests(_Conv):
    def test_unread_counts_per_student_and_clearing_them(self):
        other = self.sibling()
        a, b = self.send(), self.send(other)
        self.reply(a)
        self.reply(a, "ثانيًا")
        self.reply(b, client=self.portal(other))
        counts = self.teacher("get", "unread/").json()["counts"]
        self.assertEqual(counts, {str(self.enr.id): 2, str(other.id): 1})
        self.assertEqual(self.teacher("post", "read-replies/", {"enrollment_id": self.enr.id}).json(), {"marked": 2})
        self.assertEqual(self.teacher("get", "unread/").json()["counts"], {str(other.id): 1})
        hist = self.teacher("get", "", {"enrollment": self.enr.id}).json()["results"][0]
        self.assertTrue(all(r["read_at"] for r in hist["replies"]))

    def test_another_teacher_sees_none_of_it_and_cannot_clear_it(self):
        self.reply(self.send())
        r = self.client_b.get(SEND + "unread/", **self.with_env(self.env_b.id))
        self.assertEqual(r.json()["counts"], {})
        r = self.client_b.post(SEND + "read-replies/", {"enrollment_id": self.enr.id}, format="json",
                               **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(GuardianReply.objects.filter(read_at__isnull=True).count(), 1)

    def test_a_guardian_cannot_read_the_teachers_inbox(self):
        self.assertEqual(self.portal().get(SEND + "unread/").status_code, 403)
        self.assertEqual(self.portal().post(SEND + "read-replies/", {"enrollment_id": self.enr.id},
                                            format="json").status_code, 403)


class RankTests(_Conv):
    def setUp(self):
        super().setUp()
        self.exam = make_exam(self.env_a, self.enr, "امتحان")

    def mates(self, scores):
        """Classmates in the child's group; each sits the same exam with the given score out of 10."""
        out = []
        for i, score in enumerate(scores):
            e = self.sibling(phone=f"2015558001{i:02d}", guardian=f"2010990020{i:02d}", name=f"زميل{i}")
            self.exam.target_enrollments.add(e)
            sit(self.exam, e, 1, score)
            out.append(e)
        return out

    def rank(self):
        r = self.portal().get(OVERVIEW)
        self.assertEqual(r.status_code, 200, r.content)
        return r.json()["rank"]

    def turn_on(self, on=True):
        GuardianAlertSettings.objects.update_or_create(environment=self.env_a, defaults={"show_rank": on})

    def test_off_by_default_and_never_computed_for_the_guardian(self):
        sit(self.exam, self.enr, 1, 9)
        self.mates([5, 6, 7, 8])
        self.assertIsNone(self.rank())

    def test_position_among_classmates_when_on(self):
        self.turn_on()
        sit(self.exam, self.enr, 1, 8)
        self.mates([10, 9, 5, 4])  # me 8 -> third of five
        self.assertEqual(self.rank(), {"position": 3, "of": 5, "basis": "exam_average"})

    def test_ties_share_a_position(self):
        self.turn_on()
        sit(self.exam, self.enr, 1, 8)
        self.mates([10, 8, 8, 3])
        self.assertEqual(self.rank()["position"], 2)

    def test_too_few_classmates_shows_no_position(self):
        self.turn_on()
        sit(self.exam, self.enr, 1, 8)
        self.mates([5] * (MIN_RANKED - 2))  # with me: MIN_RANKED - 1 scored students
        self.assertEqual(self.rank(), {"position": None, "of": None, "basis": "exam_average"})

    def test_a_child_with_no_exam_has_no_position(self):
        self.turn_on()
        self.mates([5, 6, 7, 8, 9])
        self.assertIsNone(self.rank()["position"])

    def test_only_the_best_sitting_counts_and_other_groups_do_not(self):
        self.turn_on()
        sit(self.exam, self.enr, 1, 2)
        sit(self.exam, self.enr, 2, 9)  # best = 9
        self.mates([10, 8, 7, 6])
        stranger_group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        user = self.make_student_in(self.env_a, "201555800199", "غريب")
        self.activate(user)
        stranger = Enrollment.objects.create(environment=self.env_a, student=user, grade=self.grade,
                                             student_name="غريب", parent_phone="201099000999")
        stranger.groups.set([stranger_group])
        self.exam.target_enrollments.add(stranger)
        sit(self.exam, stranger, 1, 10)
        self.assertEqual(self.rank(), {"position": 2, "of": 5, "basis": "exam_average"})

    def test_the_answer_carries_no_one_elses_data(self):
        self.turn_on()
        sit(self.exam, self.enr, 1, 8)
        self.mates([10, 9, 5, 4])
        self.assertEqual(set(self.rank()), {"position", "of", "basis"})

    def test_the_teacher_switches_it_through_the_settings_endpoint(self):
        body = {"enabled": False, "absence_threshold": 3, "exam_percent_below": 50, "unpaid_after_day": 10,
                "show_rank": True}
        r = self.client_a.put(SEND + "settings/", body, format="json", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertTrue(r.json()["show_rank"])
        self.assertTrue(GuardianAlertSettings.objects.get(environment=self.env_a).show_rank)
        self.assertFalse(GuardianAlertSettings.objects.filter(environment=self.env_b, show_rank=True).exists())
        # a client that does not know the field leaves the choice alone
        body.pop("show_rank")
        r = self.client_a.put(SEND + "settings/", body, format="json", **self.with_env(self.env_a.id))
        self.assertTrue(r.json()["show_rank"])
        self.assertEqual(GuardianMessage.objects.count(), 0)
