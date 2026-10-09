"""Housekeeping: delete expired/used OTP flows so the table (which holds OTP
hashes and phone/email targets) never accumulates. Run daily from cron."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from accounts.models import PendingAuth


class Command(BaseCommand):
    help = "Deletes PendingAuth rows older than --hours (default 24)."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(hours=options["hours"])
        n, _ = PendingAuth.objects.filter(created_at__lt=cutoff).delete()
        self.stdout.write(self.style.SUCCESS(f"Purged {n} expired pending-auth row(s)."))
