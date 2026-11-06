"""
Writes the automatic warnings for guardians (parents/guardian_alerts.py). Safe to run as often as you like: a
warning already written for a child and period is never written twice.

Usage:
    python manage.py process_guardian_alerts
    python manage.py process_guardian_alerts --loop --interval 3600     # long-running
"""
import argparse
import time

from django.core.management.base import BaseCommand

from parents.guardian_alerts import run_all


class Command(BaseCommand):
    help = "Writes automatic warnings to guardians for teachers who turned them on."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running.")
        parser.add_argument("--interval", type=float, default=3600.0, help="Seconds between runs in --loop mode.")
        parser.add_argument("--max-iterations", type=int, default=0, help=argparse.SUPPRESS)

    def handle(self, *args, **options):
        iteration = 0
        while True:
            self.stdout.write(self.style.SUCCESS(f"Wrote {run_all()} guardian warning(s)."))
            iteration += 1
            if not options["loop"] or (options["max_iterations"] and iteration >= options["max_iterations"]):
                break
            time.sleep(options["interval"])
