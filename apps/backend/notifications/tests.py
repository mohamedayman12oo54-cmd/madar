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
