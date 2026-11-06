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
from notifications.delivery import deliver_pending


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
        r = deliver_pending(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(
            f"Processed {r['sent'] + r['failed'] + r['expired']} notification(s): "
            f"{r['sent']} sent, {r['failed']} failed" + (f", {r['expired']} expired." if r["expired"] else ".")))
