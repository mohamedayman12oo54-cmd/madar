"""A video aimed at grade + group reaches ONLY that group - and the teacher
sees exactly one log line for it, not one per student."""
from academics.models import Enrollment, Group
from notifications.models import Notification

from .models import ContentItem
from environments.tenancy_testing import PASSWORD

from .test_video import _Base


class TargetingTests(_Base):
    def setUp(self):
        super().setUp()
        # Same grade, DIFFERENT group.
        self.group2 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")
        self.other = self.make_student_in(self.env_a, "201555700002", "زميل")
        self.other.set_password(PASSWORD)
        self.other.is_active = True
        self.other.is_verified = True
        self.other.save()
        self.enr2 = Enrollment.objects.create(
            environment=self.env_a, student=self.other, grade=self.grade, parent_phone="201111000002")
        self.enr2.groups.set([self.group2])
        # Same grade, no group at all.
        self.third = self.make_student_in(self.env_a, "201555700003", "ثالث")
        self.enr3 = Enrollment.objects.create(
            environment=self.env_a, student=self.third, grade=self.grade, parent_phone="201111000003")

    def target(self, grades=(), groups=()):
        self.item.target_grades.set(grades)
        self.item.target_groups.set(groups)

    def publish_via_api(self):
        return self.client_a.post(f"/api/v1/content/{self.item.id}/publish/", {}, **self.with_env(self.env_a.id))

    def test_grade_and_group_reaches_only_that_group(self):
        self.target([self.grade], [self.group])
        ids = set(self.item.audience().values_list("pk", flat=True))
        self.assertEqual(ids, {self.enr.pk})
        self.assertEqual(list(ContentItem.visible_to(self.enr)), [])  # still a draft
        self.publish()
        self.assertEqual([i.pk for i in ContentItem.visible_to(self.enr)], [self.item.pk])
        self.assertEqual(list(ContentItem.visible_to(self.enr2)), [])
        self.assertEqual(list(ContentItem.visible_to(self.enr3)), [])

    def test_grade_alone_is_the_whole_grade_and_group_alone_is_that_group(self):
        self.target([self.grade], [])
        self.assertEqual(self.item.audience().count(), 3)
        self.target([], [self.group2])
        self.assertEqual({e.pk for e in self.item.audience()}, {self.enr2.pk})

    def test_publish_notifies_only_the_group_and_logs_one_line(self):
        self.target([self.grade], [self.group])
        r = self.publish_via_api()
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.data["notified"], 1)
        self.assertEqual(Notification.objects.filter(type="new_video").count(), 1)
        self.assertFalse(Notification.objects.filter(recipient=self.other).exists())

        # Make the audience bigger: a second delivery must still be ONE log row.
        self.enr3.groups.set([self.group])
        extra = Notification.objects.create(
            environment=self.env_a, recipient=self.third, enrollment=self.enr3,
            type="new_video", title="فيديو جديد", content_item=self.item)
        self.assertTrue(extra.pk)
        log = self.client_a.get("/api/v1/notifications/?type=new_video", **self.with_env(self.env_a.id)).data
        rows = log["results"] if isinstance(log, dict) else log
        self.assertEqual(len(rows), 1)
        ci = rows[0]["content_item"]
        self.assertEqual(ci["title"], "درس")
        self.assertEqual(ci["grades"], ["أول"])
        self.assertEqual(ci["groups"], ["G1"])
        full = self.client_a.get("/api/v1/notifications/?type=new_video&collapse=0", **self.with_env(self.env_a.id)).data
        self.assertEqual(len(full["results"] if isinstance(full, dict) else full), 2)

    def test_student_detail_only_for_targeted_students(self):
        self.target([self.grade], [self.group])
        self.publish()
        ok = self.student_client().get(f"/api/v1/student/videos/{self.item.id}/", **self.with_env(self.env_a.id))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["title"], "درس")
        # same grade, other group: indistinguishable from "does not exist"
        c2 = self.student_client(phone=self.other.phone)
        self.assertEqual(c2.get(f"/api/v1/student/videos/{self.item.id}/", **self.with_env(self.env_a.id)).status_code, 404)
        self.assertEqual(c2.get("/api/v1/student/videos/", **self.with_env(self.env_a.id)).data["results"], [])
