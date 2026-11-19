"""Hands queued platform notices (sent from the Control Center) to the push service.

    python manage.py process_platform_notices
    python manage.py process_platform_notices --loop --interval 10
"""
import argparse
import time

from django.core.management.base import BaseCommand

from control.jobs import record_run
from control.platform_notices import deliver_queued


class Command(BaseCommand):
    help = "Delivers queued platform notices by Web Push."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=500)
        parser.add_argument("--loop", action="store_true")
        parser.add_argument("--interval", type=float, default=10.0)
        parser.add_argument("--max-iterations", type=int, default=0, help=argparse.SUPPRESS)

    def handle(self, *args, **o):
        i = 0
        while True:
            with record_run("process_platform_notices") as run:
                r = deliver_queued(limit=o["limit"])
                run.processed = sum(r.values())
                run.failed = r["failed"]
            self.stdout.write(self.style.SUCCESS(
                f"{r['sent']} sent, {r['failed']} failed, {r['no_device']} without a device."))
            i += 1
            if not o["loop"] or (o["max_iterations"] and i >= o["max_iterations"]):
                break
            time.sleep(o["interval"])
