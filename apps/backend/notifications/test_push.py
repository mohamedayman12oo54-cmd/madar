"""Web Push: device subscription rules, delivery through the real worker, cleanup of dead devices."""
import base64
import os
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from django.core.management import call_command
from django.test import override_settings
from rest_framework.test import APIClient

from academics.models import Grade, Group
from accounts.testing import make_enrollment
from environments.tenancy_testing import PASSWORD, TenantTestCase
from notifications import webpush
from notifications.models import Notification, PushSubscription
from notifications.services import notify_enrollment

B = "/api/v1/notifications/push/"


def b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def real_keys():
    from py_vapid import Vapid

    v = Vapid()
    v.generate_keys()
    pub = v.public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return b64(pub), b64(v.private_key.private_numbers().private_value.to_bytes(32, "big"))


def browser_sub(endpoint="https://fcm.googleapis.com/fcm/send/abc123"):
    """What a browser's PushManager.subscribe() would hand us (a real P-256 key + auth secret)."""
    k = ec.generate_private_key(ec.SECP256R1())
    pub = k.public_key().public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    return {"endpoint": endpoint, "p256dh": b64(pub), "auth": b64(os.urandom(16))}


class PushBase(TenantTestCase):
    def setUp(self):
        super().setUp()
        grade = Grade.objects.create(environment=self.env_a, name="أول", fee_amount=1)
        group = Group.objects.create(environment=self.env_a, grade=grade, name="G")
        user = self.make_student_in(self.env_a, "201555500001", "أحمد")
        user.is_active = True
        user.set_password(PASSWORD)
        user.save()
        self.enrollment = make_enrollment(self.env_a, user, grade, group)
        self.user = user
        self.student = APIClient()
        tok = self.student.post("/api/v1/auth/student/login/", {"phone": "+201555500001", "password": PASSWORD}).data["access"]
        self.student.credentials(HTTP_AUTHORIZATION="Bearer " + tok)


class SubscriptionApiTests(PushBase):
    def test_requires_login(self):
        self.assertEqual(APIClient().post(B + "subscribe/", browser_sub(), format="json").status_code, 401)

    def test_subscribe_is_idempotent_and_moves_between_accounts(self):
        sub = browser_sub()
        self.assertEqual(self.student.post(B + "subscribe/", sub, format="json").status_code, 201)
        self.student.post(B + "subscribe/", sub, format="json")
        self.assertEqual(PushSubscription.objects.count(), 1)
        # the same browser, now signed in as the teacher: the device moves, the student stops receiving
        self.client_a.post(B + "subscribe/", sub, format="json")
        self.assertNotEqual(PushSubscription.objects.get().user_id, self.user.pk)

    def test_non_https_or_credentialed_endpoints_are_refused(self):
        for bad in ("http://fcm.googleapis.com/x", "https://user:pw@evil.example/x", "ftp://x/y", "javascript:alert(1)"):
            r = self.student.post(B + "subscribe/", {**browser_sub(), "endpoint": bad}, format="json")
            self.assertEqual(r.status_code, 400, bad)

    def test_unsubscribe_only_removes_own_device(self):
        sub = browser_sub()
        self.student.post(B + "subscribe/", sub, format="json")
        self.client_a.post(B + "unsubscribe/", {"endpoint": sub["endpoint"]}, format="json")  # someone else
        self.assertEqual(PushSubscription.objects.count(), 1)
        self.student.post(B + "unsubscribe/", {"endpoint": sub["endpoint"]}, format="json")
        self.assertEqual(PushSubscription.objects.count(), 0)

    def test_public_key_reports_whether_push_is_configured(self):
        self.assertFalse(self.student.get(B + "public-key/").json()["enabled"])
        pub, priv = real_keys()
        with override_settings(VAPID_PUBLIC_KEY=pub, VAPID_PRIVATE_KEY=priv):
            body = self.student.get(B + "public-key/").json()
        self.assertTrue(body["enabled"])
        self.assertEqual(body["public_key"], pub)


class DeliveryTests(PushBase):
    def setUp(self):
        super().setUp()
        self.pub, self.priv = real_keys()
        self.sub = browser_sub()
        self.student.post(B + "subscribe/", self.sub, format="json")

    def test_real_encryption_and_vapid_signing_reach_the_push_service(self):
        """Uses the REAL pywebpush crypto; only the final HTTP POST is intercepted."""
        resp = mock.Mock(status_code=201, text="")
        with override_settings(VAPID_PUBLIC_KEY=self.pub, VAPID_PRIVATE_KEY=self.priv), \
             mock.patch("pywebpush.requests.post", return_value=resp) as post:
            n = notify_enrollment(self.enrollment, Notification.Type.ABSENT, "تم تسجيل غيابك", "تفاصيل")
            call_command("process_notifications")
        self.assertEqual(post.call_count, 1)
        args, kwargs = post.call_args
        self.assertEqual(args[0], self.sub["endpoint"])
        self.assertIn("vapid", kwargs["headers"]["authorization"].lower())
        self.assertEqual(kwargs["headers"]["content-encoding"], "aes128gcm")
        self.assertNotIn("تم تسجيل".encode(), kwargs["data"])  # the payload is encrypted on the wire
        n.refresh_from_db()
        self.assertEqual(n.delivery_status, "sent")

    def test_gone_subscription_is_removed_and_not_a_failure(self):
        with override_settings(VAPID_PUBLIC_KEY=self.pub, VAPID_PRIVATE_KEY=self.priv), \
             mock.patch("notifications.webpush._send_one", return_value=(False, True, "push 410")):
            n = notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
            call_command("process_notifications")
        self.assertEqual(PushSubscription.objects.count(), 0)
        n.refresh_from_db()
        self.assertEqual(n.delivery_status, "sent")

    def test_unreachable_device_marks_failed_so_retry_can_pick_it_up(self):
        with override_settings(VAPID_PUBLIC_KEY=self.pub, VAPID_PRIVATE_KEY=self.priv), \
             mock.patch("notifications.webpush._send_one", return_value=(False, False, "Timeout")):
            n = notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
            call_command("process_notifications")
        n.refresh_from_db()
        self.assertEqual(n.delivery_status, "failed")
        self.assertEqual(PushSubscription.objects.count(), 1)

    def test_user_with_no_device_is_still_delivered_in_app(self):
        PushSubscription.objects.all().delete()
        with override_settings(VAPID_PUBLIC_KEY=self.pub, VAPID_PRIVATE_KEY=self.priv):
            n = notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
            call_command("process_notifications")
        n.refresh_from_db()
        self.assertEqual(n.delivery_status, "sent")

    def test_without_keys_the_old_null_provider_is_used(self):
        with mock.patch("notifications.webpush._send_one") as send:
            notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
            call_command("process_notifications")
        send.assert_not_called()

    def test_platform_notice_reaches_only_the_chosen_audience(self):
        with override_settings(VAPID_PUBLIC_KEY=self.pub, VAPID_PRIVATE_KEY=self.priv), \
             mock.patch("notifications.webpush._send_one", return_value=(True, False, "")) as send:
            call_command("send_platform_notice", "--audience", "teachers", "--title", "t")
            self.assertEqual(send.call_count, 0)  # only a student is subscribed
            call_command("send_platform_notice", "--audience", "students", "--title", "t")
            self.assertEqual(send.call_count, 1)
