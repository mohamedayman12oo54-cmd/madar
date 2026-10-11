"""Teacher's sent-log, manual broadcast, retry and the delivery worker."""
from django.core.management import call_command

from academics.models import Grade, Group
from accounts.testing import make_enrollment
from environments.tenancy_testing import TenantTestCase

from .models import Notification

N = "/api/v1/notifications/"


class NotificationTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=1)
        self.grade2 = Grade.objects.create(environment=self.env_a, name="ثاني", fee_amount=1)
        self.g1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.s1 = self.make_student_in(self.env_a, "201013300001", name="أحمد")
        self.s2 = self.make_student_in(self.env_a, "201013300002", name="سارة")
        self.s3 = self.make_student_in(self.env_a, "201013300003", name="علي")
        self.e1 = make_enrollment(self.env_a, self.s1, self.grade, self.g1)
        self.e2 = make_enrollment(self.env_a, self.s2, self.grade2)
        self.e3 = make_enrollment(self.env_a, self.s3, self.grade, is_active=False)

    def broadcast(self, body, client=None, env=None):
        return (client or self.client_a).post(N + "broadcast/", body, format="json", **self.with_env((env or self.env_a).id))

    def test_broadcast_to_grade_reaches_active_students_only_once(self):
        r = self.broadcast({"title": "تنبيه", "body": "غدًا الحصة", "grade_ids": [self.grade.id], "group_ids": [self.g1.id]})
        self.assertEqual((r.status_code, r.json()["recipients"]), (201, 1))  # e3 inactive, e2 other grade, e1 deduped
        n = Notification.objects.get()
        self.assertEqual((n.type, n.recipient_id, n.delivery_status), ("broadcast", self.s1.id, "pending"))

    def test_broadcast_validation(self):
        self.assertEqual(self.broadcast({"title": "x", "grade_ids": [self.grade.id]}).status_code, 400)  # title too short
        self.assertEqual(self.broadcast({"title": "عنوان"}).status_code, 400)  # no target
        self.assertEqual(self.broadcast({"title": "عنوان", "grade_ids": [999999]}).status_code, 400)
        other = Grade.objects.create(environment=self.env_b, name="ب", fee_amount=1)
        self.assertEqual(self.broadcast({"title": "عنوان", "grade_ids": [other.id]}).status_code, 400)  # another teacher's grade
        self.assertEqual(Notification.objects.count(), 0)

    def test_broadcast_is_rate_limited(self):
        from unittest import mock

        from rest_framework.throttling import SimpleRateThrottle

        with mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, {"broadcast": "1/hour"}):
            codes = [self.broadcast({"title": "عنوان", "grade_ids": [self.grade.id]}).status_code for _ in range(2)]
        self.assertEqual(codes, [201, 429])

    def test_log_is_environment_scoped_and_filterable(self):
        self.broadcast({"title": "عنوان", "grade_ids": [self.grade.id]})
        self.assertEqual(self.client_a.get(N, **self.with_env(self.env_a.id)).json()["count"], 1)
        self.assertEqual(self.client_a.get(N + "?type=absent", **self.with_env(self.env_a.id)).json()["count"], 0)
        self.assertEqual(self.client_b.get(N, **self.with_env(self.env_b.id)).json()["count"], 0)
        self.assert_cross_tenant_denied("get", N)
        self.assert_cross_tenant_denied("post", N + "broadcast/", body={"title": "عنوان", "grade_ids": [1]})

    def test_worker_delivers_and_failed_can_be_requeued(self):
        self.broadcast({"title": "عنوان", "grade_ids": [self.grade.id]})
        call_command("process_notifications")
        self.assertEqual(Notification.objects.get().delivery_status, "sent")
        Notification.objects.update(delivery_status="failed", delivery_error="boom")
        self.assertEqual(self.client_a.get(N + "summary/", **self.with_env(self.env_a.id)).json()["failed"], 1)
        r = self.client_a.post(N + "retry-failed/", **self.with_env(self.env_a.id))
        self.assertEqual(r.json()["requeued"], 1)
        self.assertEqual(Notification.objects.get().delivery_status, "pending")

    def test_log_shows_the_teacher_scoped_name_not_the_global_one(self):
        self.e1.student_name = "اسم عند المعلم"
        self.e1.save()
        self.broadcast({"title": "عنوان", "grade_ids": [self.grade.id]})
        row = self.client_a.get(N, **self.with_env(self.env_a.id)).json()["results"][0]
        self.assertEqual(row["student"]["name"], "اسم عند المعلم")


class BroadcastTargetingTests(TenantTestCase):
    """Choosing a grade AND a group must NARROW to that group, not union."""

    URL = "/api/v1/notifications/broadcast/"
    LOG = "/api/v1/notifications/broadcasts/"

    def setUp(self):
        super().setUp()
        from academics.models import Enrollment, Grade, Group

        self.grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.other_grade = Grade.objects.create(environment=self.env_a, name="ثاني")
        self.g1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.g2 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G2")

        def enrol(phone, name, grade, group):
            e = Enrollment.objects.create(
                environment=self.env_a, student=self.make_student_in(self.env_a, phone, name),
                grade=grade, student_name=name, parent_phone="201111000001")
            if group:
                e.groups.set([group])
            return e

        self.in_g1 = enrol("201555910001", "في-G1", self.grade, self.g1)
        self.in_g2 = enrol("201555910002", "في-G2", self.grade, self.g2)
        self.other = enrol("201555910003", "صف-آخر", self.other_grade, None)

    def send(self, grade_ids=(), group_ids=(), title="عنوان", body="نص"):
        return self.client_a.post(self.URL, {
            "title": title, "body": body,
            "grade_ids": list(grade_ids), "group_ids": list(group_ids),
        }, format="json", **self.with_env(self.env_a.id))

    def recipients_of(self, response):
        from notifications.models import Notification

        return set(Notification.objects.filter(broadcast_id=response.json()["id"])
                   .values_list("enrollment_id", flat=True))

    def test_grade_plus_group_reaches_only_that_group(self):
        r = self.send(grade_ids=[self.grade.id], group_ids=[self.g1.id])
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(self.recipients_of(r), {self.in_g1.id},
                         "a message aimed at one group must not hit the whole grade")
        self.assertEqual(r.json()["recipients"], 1)

    def test_grade_only_reaches_the_whole_grade(self):
        r = self.send(grade_ids=[self.grade.id])
        self.assertEqual(self.recipients_of(r), {self.in_g1.id, self.in_g2.id})

    def test_group_only_reaches_that_group(self):
        r = self.send(group_ids=[self.g2.id])
        self.assertEqual(self.recipients_of(r), {self.in_g2.id})

    def test_a_student_in_another_grade_is_never_included(self):
        r = self.send(grade_ids=[self.grade.id], group_ids=[self.g1.id])
        self.assertNotIn(self.other.id, self.recipients_of(r))

    def test_the_log_shows_one_entry_per_message_not_per_student(self):
        self.send(grade_ids=[self.grade.id])          # 2 recipients
        rows = self.client_a.get(self.LOG, **self.with_env(self.env_a.id)).json()["results"]
        self.assertEqual(len(rows), 1, "two deliveries must appear as ONE message")
        self.assertEqual(rows[0]["recipient_count"], 2)
        self.assertEqual(rows[0]["grades"], ["أول"])

    def test_the_detail_view_lists_who_received_it(self):
        sent = self.send(grade_ids=[self.grade.id], group_ids=[self.g1.id])
        detail = self.client_a.get(f"{self.LOG}{sent.json()['id']}/",
                                   **self.with_env(self.env_a.id)).json()
        self.assertEqual(detail["groups"], ["G1"])
        self.assertEqual([r["enrollment_id"] for r in detail["recipients"]], [self.in_g1.id])

    def test_another_teacher_cannot_read_my_broadcasts(self):
        sent = self.send(grade_ids=[self.grade.id])
        self.assertEqual(self.client_b.get(self.LOG, **self.with_env(self.env_b.id)).json()["results"], [])
        self.assertEqual(self.client_b.get(f"{self.LOG}{sent.json()['id']}/",
                                           **self.with_env(self.env_b.id)).status_code, 404)

    def test_the_student_can_open_the_full_message(self):
        self.send(grade_ids=[self.grade.id], group_ids=[self.g1.id], body="نص الرسالة الكامل")
        from accounts.models import User

        student = User.objects.get(pk=self.in_g1.student_id)
        student.is_active = True
        student.is_verified = True
        student.set_password("Str0ng!Pass")
        student.save()
        from rest_framework.test import APIClient

        c = APIClient()
        tok = c.post("/api/v1/auth/student/login/",
                     {"phone": student.phone, "password": "Str0ng!Pass"}).data["access"]
        c.credentials(HTTP_AUTHORIZATION="Bearer " + tok)
        rows = c.get("/api/v1/student/notifications/", **self.with_env(self.env_a.id)).json()["results"]
        details = rows[0]["details"]
        self.assertEqual(details["body"], "نص الرسالة الكامل")
        self.assertEqual(details["groups"], ["G1"])


class BroadcastLogCollapseTests(TenantTestCase):
    """A message to many students is ONE log row, not one row per student."""

    LOG = "/api/v1/notifications/"

    def setUp(self):
        super().setUp()
        from academics.models import Enrollment, Grade, Group

        self.grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.group = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        for i in range(4):
            e = Enrollment.objects.create(
                environment=self.env_a,
                student=self.make_student_in(self.env_a, f"20155592000{i}", f"ط{i}"),
                grade=self.grade, student_name=f"ط{i}", parent_phone="201111000001")
            e.groups.set([self.group])
        self.client_a.post("/api/v1/notifications/broadcast/", {
            "title": "إعلان", "body": "نص", "grade_ids": [self.grade.id], "group_ids": [self.group.id],
        }, format="json", **self.with_env(self.env_a.id))

    def rows(self, **params):
        r = self.client_a.get(self.LOG, params, **self.with_env(self.env_a.id))
        body = r.json()
        return body["results"] if isinstance(body, dict) else body

    def test_four_deliveries_appear_as_one_log_row(self):
        from notifications.models import Notification

        self.assertEqual(Notification.objects.filter(type="broadcast").count(), 4,
                         "all four students still receive it")
        rows = [r for r in self.rows() if r["type"] == "broadcast"]
        self.assertEqual(len(rows), 1, "the log must show ONE message")

    def test_the_row_names_the_audience_not_one_student(self):
        row = next(r for r in self.rows() if r["type"] == "broadcast")
        self.assertEqual(row["broadcast"]["recipient_count"], 4)
        self.assertEqual(row["broadcast"]["groups"], ["G1"])
        self.assertEqual(row["broadcast"]["grades"], ["أول"])

    def test_per_student_events_are_not_collapsed(self):
        """Only broadcasts collapse; an absence per student must stay visible."""
        from academics.models import Enrollment
        from notifications.services import notify_many
        from notifications.models import Notification

        notify_many(list(Enrollment.objects.filter(environment=self.env_a)),
                    Notification.Type.ABSENT, "غياب")
        rows = [r for r in self.rows() if r["type"] == "absent"]
        self.assertEqual(len(rows), 4, "individual events must not be merged")

    def test_the_full_audience_is_still_reachable(self):
        row = next(r for r in self.rows() if r["type"] == "broadcast")
        detail = self.client_a.get(f"/api/v1/notifications/broadcasts/{row['broadcast']['id']}/",
                                   **self.with_env(self.env_a.id)).json()
        self.assertEqual(len(detail["recipients"]), 4)
