"""Delivery guarantees: sent once, never double-sent, stale ones expire, and delivery starts by itself when a
notification is saved (no separate worker needed)."""
from datetime import timedelta
from unittest import mock

from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone

from notifications import delivery, dispatch
from notifications.models import Notification
from notifications.services import notify_enrollment, notify_many

from .test_push import B, PushBase, browser_sub, real_keys


class DeliveryGuaranteeTests(PushBase):
    def setUp(self):
        super().setUp()
        self.pub, self.priv = real_keys()
        self.student.post(B + "subscribe/", browser_sub(), format="json")

    def keys(self):
        return override_settings(VAPID_PUBLIC_KEY=self.pub, VAPID_PRIVATE_KEY=self.priv)

    def test_a_notification_is_pushed_exactly_once_however_often_the_worker_runs(self):
        with self.keys(), mock.patch("notifications.webpush._send_one", return_value=(True, False, "")) as send:
            notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
            for _ in range(3):
                call_command("process_notifications")
        self.assertEqual(send.call_count, 1)

    def test_a_row_another_worker_already_delivered_is_skipped(self):
        with self.keys(), mock.patch("notifications.webpush._send_one", return_value=(True, False, "")) as send:
            n = notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
            real = Notification.objects.select_for_update

            def race(*a, **kw):
                # between listing the row and claiming it, a second worker finished it
                Notification.objects.filter(pk=n.pk).update(delivery_status="sent")
                return real(*a, **kw)

            with mock.patch.object(Notification.objects, "select_for_update", side_effect=race):
                result = delivery.deliver_pending()
        send.assert_not_called()
        self.assertEqual(result, {"sent": 0, "failed": 0, "expired": 0})

    def test_a_stale_notification_expires_instead_of_arriving_days_late(self):
        with self.keys(), mock.patch("notifications.webpush._send_one", return_value=(True, False, "")) as send:
            n = notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
            Notification.objects.filter(pk=n.pk).update(created_at=timezone.now() - timedelta(hours=49))
            fresh = notify_enrollment(self.enrollment, Notification.Type.ABSENT, "y")
            result = delivery.deliver_pending()
        self.assertEqual(result, {"sent": 1, "failed": 0, "expired": 1})
        self.assertEqual(send.call_count, 1)
        n.refresh_from_db(); fresh.refresh_from_db()
        self.assertEqual((n.delivery_status, n.delivery_error), ("failed", delivery.EXPIRED))
        self.assertEqual(fresh.delivery_status, "sent")

    @override_settings(NOTIFICATION_MAX_AGE_HOURS=1)
    def test_the_expiry_window_is_configurable(self):
        with self.keys(), mock.patch("notifications.webpush._send_one", return_value=(True, False, "")):
            n = notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
            Notification.objects.filter(pk=n.pk).update(created_at=timezone.now() - timedelta(hours=2))
            self.assertEqual(delivery.deliver_pending()["expired"], 1)

    def test_the_command_reports_expired_ones(self):
        n = notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
        Notification.objects.filter(pk=n.pk).update(created_at=timezone.now() - timedelta(hours=60))
        from io import StringIO
        out = StringIO()
        call_command("process_notifications", stdout=out)
        self.assertIn("1 expired", out.getvalue())


class DispatchTests(PushBase):
    """`kick()` is what makes a push go out without a separate worker process."""

    @override_settings(NOTIFICATION_WORKER_MODE="thread")
    def test_saving_a_notification_starts_delivery_after_the_transaction_commits(self):
        with mock.patch.object(dispatch, "_start") as start:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
                start.assert_not_called()  # not before commit: a rolled-back request must start nothing
        self.assertEqual(len(callbacks), 1)
        start.assert_called_once()

    @override_settings(NOTIFICATION_WORKER_MODE="thread")
    def test_a_fan_out_is_one_kick_and_an_empty_one_is_none(self):
        with mock.patch.object(dispatch, "_start") as start:
            with self.captureOnCommitCallbacks(execute=True):
                notify_many([self.enrollment], Notification.Type.BROADCAST, "t")
                notify_many([], Notification.Type.BROADCAST, "t")
        start.assert_called_once()

    def test_external_mode_starts_nothing(self):
        with mock.patch.object(dispatch, "_start") as start:
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                notify_enrollment(self.enrollment, Notification.Type.ABSENT, "x")
        self.assertEqual(callbacks, [])
        start.assert_not_called()

    def test_tests_run_in_external_mode(self):
        from django.conf import settings
        self.assertEqual(settings.NOTIFICATION_WORKER_MODE, "external")

    def test_one_drain_thread_at_a_time_and_a_late_arrival_triggers_another_pass(self):
        passes = []

        def fake_deliver(*a, **kw):
            passes.append(1)
            if len(passes) == 1:
                dispatch._start()  # a notification saved while the first pass is running
            return {"sent": 0, "failed": 0, "expired": 0}

        with mock.patch("notifications.delivery.deliver_pending", side_effect=fake_deliver), \
                mock.patch.object(dispatch.threading, "Thread") as thread:
            dispatch._running = False
            dispatch._start()
            thread.assert_called_once()
            dispatch._start()               # already running: no second thread
            thread.assert_called_once()
            dispatch._running = True        # as the thread would have it
            dispatch._rerun = False
            with mock.patch.object(dispatch, "connections"):
                dispatch._drain()
        self.assertEqual(len(passes), 2)    # the first pass, plus one more for the late arrival
        self.assertFalse(dispatch._running)
