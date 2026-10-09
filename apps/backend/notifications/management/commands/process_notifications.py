"""
Phase 5 async worker — run periodically (cron/systemd timer/etc.) outside
the request/response cycle. This is the "management-command worker inside
the same Django codebase" the architecture spec explicitly sanctions for
V1 (no message broker exists in this project, and none is introduced here).

Usage:
    python manage.py process_notifications
    python manage.py process_notifications --limit 50
    python manage.py process_notifications --loop --interval 5      # long-running
"""
import argparse
import time

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from notifications.models import Notification
from notifications.providers import get_provider


class Command(BaseCommand):
    help = "Delivers PENDING notifications via the configured push provider."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)
        parser.add_argument("--loop", action="store_true", help="Keep running, polling for new work.")
        parser.add_argument("--interval", type=float, default=5.0, help="Seconds between polls in --loop mode.")
        parser.add_argument("--max-iterations", type=int, default=0, help=argparse.SUPPRESS)

    def handle(self, *args, **options):
        iteration = 0
        while True:
            self.run_once(options)
            iteration += 1
            if not options["loop"] or (options["max_iterations"] and iteration >= options["max_iterations"]):
                break
            time.sleep(options["interval"])

    def run_once(self, options):
        provider = get_provider()
        pending = Notification.objects.filter(delivery_status=Notification.DeliveryStatus.PENDING)[: options["limit"]]

        sent = failed = 0
        for notification in pending:
            result = provider.send(notification)
            with transaction.atomic():
                if result.success:
                    notification.delivery_status = Notification.DeliveryStatus.SENT
                    notification.delivered_at = timezone.now()
                    notification.delivery_error = ""
                    sent += 1
                else:
                    notification.delivery_status = Notification.DeliveryStatus.FAILED
                    notification.delivery_error = result.error[:255]
                    failed += 1
                notification.save(update_fields=["delivery_status", "delivered_at", "delivery_error"])

        self.stdout.write(self.style.SUCCESS(f"Processed {sent + failed} notification(s): {sent} sent, {failed} failed."))
