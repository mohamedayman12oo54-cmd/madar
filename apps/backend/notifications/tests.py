"""Phase 5 — Notifications: transactional creation with the domain event,
per-recipient + per-tenant scoping, and the asynchronous delivery worker."""
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.utils import timezone

from academics.models import Enrollment, Grade, Group
from environments.tenancy_testing import TenantTestCase
from scheduling.models import SessionInstance

from .models import Notification
from .providers import DeliveryResult, NullPushProvider, PushProvider

LIST_URL = "/api/v1/notifications/"
UNREAD_URL = "/api/v1/notifications/unread-count/"


def read_url(pk):
    return f"/api/v1/notifications/{pk}/read/"


class NotificationSetupMixin:
    def setUp(self):
        super().setUp()
        grade = Grade.objects.create(environment=self.env_a, name="أول")
        self.group = Group.objects.create(environment=self.env_a, grade=grade, name="G1")
        self.session = SessionInstance.objects.create(environment=self.env_a, group=self.group, scheduled_at=timezone.now())


class TransactionalCreationTests(NotificationSetupMixin, TenantTestCase):
    def test_opening_a_session_creates_a_pending_notification_for_the_owner(self):
        self.session.open()
        n = Notification.objects.get()
        self.assertEqual(n.recipient_id, self.teacher_a.id)
        self.assertEqual(n.environment_id, self.env_a.id)
        self.assertEqual(n.type, Notification.Type.SESSION_OPENED)
        self.assertEqual(n.delivery_status, Notification.DeliveryStatus.PENDING)
        self.assertEqual(n.session_id, self.session.id)

    def test_reopening_creates_a_second_independent_notification_and_leaves_the_first_alone(self):
        self.session.open()
        first = Notification.objects.get()
        first.delivery_status = Notification.DeliveryStatus.SENT
        first.save(update_fields=["delivery_status"])
        self.session.close()
        self.session.reopen()

        self.assertEqual(Notification.objects.count(), 2)
        first.refresh_from_db()
        self.assertEqual(first.type, Notification.Type.SESSION_OPENED)
        self.assertEqual(first.delivery_status, Notification.DeliveryStatus.SENT)  # untouched
        self.assertTrue(Notification.objects.filter(type=Notification.Type.SESSION_REOPENED).exists())

    def test_closing_a_session_does_not_notify(self):
        self.session.open()
        Notification.objects.all().delete()
        self.session.close()
        self.assertEqual(Notification.objects.count(), 0)

    def test_failed_domain_save_rolls_back_the_notification_and_the_status_change(self):
        """The whole point of the outbox pattern: if anything in the same
        atomic block fails, nothing — including the notification — is kept."""
        with mock.patch.object(SessionInstance, "_sync_roster", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.session.open()
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionInstance.Status.PLANNED)
        self.assertEqual(Notification.objects.count(), 0)

    def test_failed_notification_creation_rolls_back_the_session_open(self):
        with mock.patch("notifications.services.Notification.objects.create", side_effect=RuntimeError("boom")):
            with self.assertRaises(RuntimeError):
                self.session.open()
        self.session.refresh_from_db()
        self.assertEqual(self.session.status, SessionInstance.Status.PLANNED)

    def test_invalid_transition_creates_no_notification(self):
        with self.assertRaises(Exception):
            self.session.close()  # planned -> close is invalid
        self.assertEqual(Notification.objects.count(), 0)

    def test_api_open_creates_the_notification_too(self):
        r = self.client_a.post(f"/api/v1/scheduling/sessions/{self.session.id}/open/", **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        self.assertEqual(Notification.objects.count(), 1)


class NotificationApiTests(NotificationSetupMixin, TenantTestCase):
    def setUp(self):
        super().setUp()
        self.session.open()
        self.notification = Notification.objects.get()
        # A notification belonging to the OTHER teacher/environment.
        grade_b = Grade.objects.create(environment=self.env_b, name="أول")
        group_b = Group.objects.create(environment=self.env_b, grade=grade_b, name="G1")
        session_b = SessionInstance.objects.create(environment=self.env_b, group=group_b, scheduled_at=timezone.now())
        session_b.open()
        self.notification_b = Notification.objects.get(environment=self.env_b)

    def _items(self, r):
        return r.json()["results"]

    def test_list_shows_only_my_own_notifications(self):
        r = self.client_a.get(LIST_URL, **self.with_env(self.env_a.id))
        ids = [n["id"] for n in self._items(r)]
        self.assertEqual(ids, [self.notification.id])

    def test_list_does_not_expose_recipient_or_environment_ids(self):
        r = self.client_a.get(LIST_URL, **self.with_env(self.env_a.id))
        keys = set(self._items(r)[0].keys())
        self.assertNotIn("recipient", keys)
        self.assertNotIn("environment", keys)

    def test_unread_filter_and_mark_read(self):
        r = self.client_a.post(read_url(self.notification.id), **self.with_env(self.env_a.id))
        self.assertEqual(r.status_code, 200)
        self.assertIsNotNone(r.json()["read_at"])
        unread = self.client_a.get(f"{LIST_URL}?unread=true", **self.with_env(self.env_a.id))
        self.assertEqual(self._items(unread), [])

    def test_mark_read_is_idempotent_and_keeps_the_first_read_time(self):
        first = self.client_a.post(read_url(self.notification.id), **self.with_env(self.env_a.id)).json()["read_at"]
        second = self.client_a.post(read_url(self.notification.id), **self.with_env(self.env_a.id)).json()["read_at"]
        self.assertEqual(first, second)

    def test_unread_count(self):
        r = self.client_a.get(UNREAD_URL, **self.with_env(self.env_a.id))
        self.assertEqual(r.json()["unread_count"], 1)
        self.client_a.post(read_url(self.notification.id), **self.with_env(self.env_a.id))
        r2 = self.client_a.get(UNREAD_URL, **self.with_env(self.env_a.id))
        self.assertEqual(r2.json()["unread_count"], 0)

    def test_cannot_mark_another_teachers_notification_read(self):
        self.assert_cross_tenant_denied("post", read_url(self.notification.id))
        # even with MY OWN valid header, someone else's id is simply not found
        r = self.client_b.post(read_url(self.notification.id), **self.with_env(self.env_b.id))
        self.assertEqual(r.status_code, 404)
        self.notification.refresh_from_db()
        self.assertIsNone(self.notification.read_at)

    def test_cross_tenant_list_is_denied(self):
        self.assert_cross_tenant_denied("get", LIST_URL)
        self.assert_cross_tenant_denied("get", UNREAD_URL)

    def test_requires_environment_header(self):
        self.assertEqual(self.client_a.get(LIST_URL).status_code, 400)


class DeliveryWorkerTests(NotificationSetupMixin, TenantTestCase):
    def setUp(self):
        super().setUp()
        self.session.open()
        self.notification = Notification.objects.get()

    def _run(self, *args):
        out = StringIO()
        call_command("process_notifications", *args, stdout=out)
        return out.getvalue()

    def test_worker_marks_pending_as_sent(self):
        out = self._run()
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.delivery_status, Notification.DeliveryStatus.SENT)
        self.assertIsNotNone(self.notification.delivered_at)
        self.assertIn("1 sent, 0 failed", out)

    def test_worker_records_a_provider_failure_without_crashing(self):
        class Failing(PushProvider):
            def send(self, notification):
                return DeliveryResult(success=False, error="provider down")

        with mock.patch("notifications.management.commands.process_notifications.get_provider", return_value=Failing()):
            self._run()
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.delivery_status, Notification.DeliveryStatus.FAILED)
        self.assertEqual(self.notification.delivery_error, "provider down")

    def test_worker_does_not_reprocess_already_sent_notifications(self):
        self._run()
        with mock.patch.object(NullPushProvider, "send") as send:
            self._run()
        send.assert_not_called()

    def test_worker_respects_limit(self):
        self.session.close(); self.session.reopen()  # a second notification
        self._run("--limit", "1")
        statuses = sorted(Notification.objects.values_list("delivery_status", flat=True))
        self.assertEqual(statuses, ["pending", "sent"])

    def test_delivery_never_happens_inside_the_request_cycle(self):
        """Opening a session via the API must leave the notification PENDING
        — delivery is only ever done by the worker."""
        session2 = SessionInstance.objects.create(environment=self.env_a, group=self.group, scheduled_at=timezone.now())
        self.client_a.post(f"/api/v1/scheduling/sessions/{session2.id}/open/", **self.with_env(self.env_a.id))
        n = Notification.objects.get(session=session2)
        self.assertEqual(n.delivery_status, Notification.DeliveryStatus.PENDING)


class LoopModeTests(NotificationSetupMixin, TenantTestCase):
    def test_loop_runs_the_requested_iterations_then_stops(self):
        self.session.open()
        with mock.patch("notifications.management.commands.process_notifications.time.sleep") as sleep:
            call_command("process_notifications", "--loop", "--interval", "0", "--max-iterations", "3", stdout=StringIO())
        self.assertEqual(sleep.call_count, 2)  # sleeps between iterations, not after the last
        self.assertEqual(Notification.objects.get().delivery_status, "sent")


class ProviderAbstractionTests(TenantTestCase):
    def test_null_provider_reports_success(self):
        self.assertTrue(NullPushProvider().send(object()).success)

    def test_base_provider_is_an_interface(self):
        with self.assertRaises(NotImplementedError):
            PushProvider().send(object())
