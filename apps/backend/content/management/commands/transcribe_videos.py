"""
Worker for lesson-video transcription, for TRANSCRIPTION_BACKGROUND=worker
(production: keep transcription out of the web process).

    python manage.py transcribe_videos
    python manage.py transcribe_videos --loop --interval 5
    python manage.py transcribe_videos --requeue-stale-minutes 360

A worker that died mid-transcription leaves a row in `processing`; rows older
than --requeue-stale-minutes are put back to `pending` first.
"""
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from content.models import Transcript
from content.transcription import run_transcription


class Command(BaseCommand):
    help = "Transcribe uploaded lesson videos that are waiting."

    def add_arguments(self, parser):
        parser.add_argument("--loop", action="store_true", help="Keep running.")
        parser.add_argument("--interval", type=int, default=5, help="Seconds between scans with --loop.")
        parser.add_argument("--requeue-stale-minutes", type=int, default=360)

    def handle(self, *args, **opts):
        while True:
            cutoff = timezone.now() - timedelta(minutes=opts["requeue_stale_minutes"])
            Transcript.objects.filter(
                status=Transcript.Status.PROCESSING, started_at__lt=cutoff,
            ).update(status=Transcript.Status.PENDING)

            ids = list(Transcript.objects.filter(
                status=Transcript.Status.PENDING).order_by("requested_at").values_list("pk", flat=True))
            for pk in ids:
                run_transcription(pk)
                row = Transcript.objects.get(pk=pk)
                self.stdout.write(f"transcript {pk}: {row.status}")
            if not opts["loop"]:
                if not ids:
                    self.stdout.write("Nothing to transcribe.")
                return
            time.sleep(opts["interval"])
