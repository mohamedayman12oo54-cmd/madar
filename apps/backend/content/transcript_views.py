"""
Transcript of an uploaded lesson video (teacher only).

    GET  /content/<item>/transcript/   -> current state (poll while it runs)
    POST /content/<item>/transcript/   -> (re)start, e.g. after a failure
"""
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember

from .models import ContentItem, Transcript
from .transcription import ensure_running, request_transcription
from .video_views import VideoUploadRateThrottle

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
NONE = {"status": "none", "language": "", "text": "", "segments": [], "duration_seconds": None,
        "word_count": 0, "error": "", "updated_at": None}


def transcript_payload(row):
    if row is None:
        return dict(NONE)
    return {
        "status": row.status, "language": row.language, "text": row.text,
        "segments": row.segments, "duration_seconds": row.duration_seconds,
        "word_count": len(row.text.split()), "error": row.error, "updated_at": row.updated_at,
    }


class TranscriptView(APIView):
    permission_classes = IS_ENV_OWNER

    def _item(self, request, pk):
        return generics.get_object_or_404(
            ContentItem.objects.filter(environment=request.environment), pk=pk)

    def get(self, request, pk):
        item = self._item(request, pk)
        row = Transcript.objects.filter(item=item).first()
        if row is not None:
            ensure_running(row)
        return Response(transcript_payload(row))

    def post(self, request, pk):
        item = self._item(request, pk)
        if not item.video_file:
            raise serializers.ValidationError({"detail": "ارفع ملف فيديو أولًا."})
        row = Transcript.objects.filter(item=item).first()
        if row is not None and row.status in (Transcript.Status.PENDING, Transcript.Status.PROCESSING):
            return Response(transcript_payload(ensure_running(row)), status=202)
        return Response(transcript_payload(request_transcription(item.pk)), status=202)
