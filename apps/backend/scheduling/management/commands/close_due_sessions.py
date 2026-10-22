"""Close every OPEN session whose end time has passed (auto-marks the unmarked as absent).
Safe to run from cron every minute; idempotent."""
from django.core.management.base import BaseCommand

from scheduling.services import close_due_sessions


class Command(BaseCommand):
    help = "Close sessions whose end time has passed (idempotent; safe for cron)."

    def handle(self, *args, **options):
        closed = close_due_sessions()
        self.stdout.write(f"Closed {closed} session(s).")
