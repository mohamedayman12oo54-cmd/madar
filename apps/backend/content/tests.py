"""Video & content: metadata + targeting + external reference; publish fires
"new video available" once to the targeted ACTIVE students."""
from academics.models import Grade, Group
from accounts.testing import make_enrollment
from environments.tenancy_testing import TenantTestCase
from notifications.models import Notification

from .models import ContentItem

C = "/api/v1/content/"
YT = "dQw4w9WgXcQ"


class ContentTests(TenantTestCase):
    def setUp(self):
        super().setUp()
        self.grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=1)
        self.g1 = Group.objects.create(environment=self.env_a, grade=self.grade, name="G1")
        self.s1 = self.make_student_in(self.env_a, "201014400001", name="أحمد")
        self.s2 = self.make_student_in(self.env_a, "201014400002", name="سارة")
        self.e1 = make_enrollment(self.env_a, self.s1, self.grade, self.g1)
        self.e2 = make_enrollment(self.env_a, self.s2, self.grade)

    def create(self, **kw):
        body = {"title": "درس 1", "video_provider": "youtube", "video_ref": YT, **kw}
        return self.client_a.post(C, body, format="json", **self.with_env(self.env_a.id))

    def publish(self, pk, client=None, env=None):
        return (client or self.client_a).post(f"{C}{pk}/publish/", **self.with_env((env or self.env_a).id))

    def test_create_with_mixed_targets_and_provider_neutral_output(self):
        r = self.create(grade_ids=[self.grade.id], group_ids=[self.g1.id], enrollment_ids=[self.e2.id])
        self.assertEqual(r.status_code, 201, r.content)
        body = r.json()
        self.assertNotIn("video_ref", body)
        self.assertFalse(body["published"])
        self.assertEqual(len(body["targets"]["grades"]) + len(body["targets"]["groups"]) + len(body["targets"]["students"]), 3)

    def test_invalid_video_reference_rejected(self):
        self.assertEqual(self.create(video_ref="javascript:alert(1)").status_code, 400)
        self.assertEqual(self.create(video_provider="youtube", video_ref="not a video").status_code, 400)

    def test_targets_must_belong_to_the_callers_environment(self):
        other = Grade.objects.create(environment=self.env_b, name="ب", fee_amount=1)
        self.assertEqual(self.create(grade_ids=[other.id]).status_code, 400)
        self.assertEqual(self.create(group_ids=[987654]).status_code, 400)
        self.assertEqual(ContentItem.objects.count(), 0)

    def test_publish_requires_a_target(self):
        pk = self.create().json()["id"]
        self.assertEqual(self.publish(pk).status_code, 400)

    def test_publish_notifies_targeted_active_students_once_and_twice_is_409(self):
        pk = self.create(group_ids=[self.g1.id]).json()["id"]
        r = self.publish(pk)
        self.assertEqual((r.status_code, r.json()["notified"]), (200, 1))
        self.assertEqual(Notification.objects.get().recipient_id, self.s1.id)
        self.assertEqual(self.publish(pk).status_code, 409)
        self.assertEqual(Notification.objects.count(), 1)

    def test_whole_grade_target_skips_inactive_students(self):
        self.e2.is_active = False
        self.e2.save()
        pk = self.create(grade_ids=[self.grade.id]).json()["id"]
        self.assertEqual(self.publish(pk).json()["notified"], 1)

    def test_cannot_touch_another_teachers_content(self):
        pk = self.create(grade_ids=[self.grade.id]).json()["id"]
        self.assert_cross_tenant_denied("get", C)
        self.assertEqual(self.publish(pk, client=self.client_b, env=self.env_b).status_code, 404)
        r = self.client_b.delete(f"{C}{pk}/", **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)
        self.assertEqual(ContentItem.objects.count(), 1)
