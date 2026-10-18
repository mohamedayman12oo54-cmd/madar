"""
Video upload (teacher) and protected playback (teacher + student).

Authorisation is re-checked on EVERY request, including at stream time, so a
ticket issued a minute ago stops working the instant the item is unpublished,
un-targeted, deleted, or the student's enrolment is deactivated.
"""
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from django.http import Http404
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment
from accounts.models import User
from accounts.permissions import IsStudent, IsTeacher
from accounts.throttles import UserRateThrottle
from environments.tenancy import IsEnvironmentMember

from .models import ContentItem, Transcript, VideoProgress
import re

from .streaming import issue_ticket, resolve_ticket_full, stream_file
from .transcode import delete_renditions, schedule_renditions
from .transcription import request_transcription
from .uploads import safe_display_name, validate_video_upload

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
IS_STUDENT = [IsStudent, IsEnvironmentMember.for_role("student")]


class VideoUploadRateThrottle(UserRateThrottle):
    """Uploads are heavy (disk + bandwidth); cap them per teacher."""
    scope = "video-upload"


def _owned_item(request, pk):
    return generics.get_object_or_404(
        ContentItem.objects.filter(environment=request.environment), pk=pk)


def _my_enrollment(request):
    return generics.get_object_or_404(
        Enrollment.objects.filter(
            environment=request.environment, student=request.user, is_active=True))


def _student_may_watch(item, enrollment):
    """The single source of truth for 'is this student allowed to watch?'.
    Used when issuing a ticket AND again when streaming."""
    if item.published_at is None:
        return False
    return item.audience().filter(pk=enrollment.pk).exists()


class VideoUploadView(APIView):
    """PUT an actual video file onto an existing item (teacher only).

    Replacing an upload deletes the previous blob, so a superseded video does
    not linger on disk and its old path cannot be streamed any more.
    """
    permission_classes = IS_ENV_OWNER
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [VideoUploadRateThrottle]

    def put(self, request, pk):
        item = _owned_item(request, pk)
        upload = request.FILES.get("video")
        try:
            validate_video_upload(upload)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"video": list(exc.messages)})

        old = item.video_file.name if item.video_file else None
        with transaction.atomic():
            item.video_file = upload
            item.source = ContentItem.Source.UPLOAD
            item.original_filename = safe_display_name(upload.name)
            item.file_size = upload.size
            item.content_type = (upload.content_type or "").split(";")[0].strip().lower()
            # An uploaded file supersedes any external reference.
            item.video_provider = "none"
            item.video_ref = ""
            item.save()
        if old and old != item.video_file.name:
            item.video_file.storage.delete(old)
        delete_renditions(item)               # copies of the OLD video must not outlive it
        schedule_renditions(item.id)
        request_transcription(item.pk)          # speech -> text for the AI quiz, in the background
        return Response({
            "id": item.id, "source": item.source,
            "original_filename": item.original_filename,
            "file_size": item.file_size, "content_type": item.content_type,
        }, status=status.HTTP_200_OK)

    def delete(self, request, pk):
        """Remove the uploaded blob; the item itself survives as a draft."""
        item = _owned_item(request, pk)
        delete_renditions(item)
        Transcript.objects.filter(item=item).delete()   # the text of a removed video must not outlive it
        if item.video_file:
            item.video_file.delete(save=False)
        item.video_file = None
        item.source = ContentItem.Source.EXTERNAL
        item.original_filename = ""
        item.file_size = None
        item.content_type = ""
        item.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


_QUALITY_RE = re.compile(r"^(\d{3,4})p?$")


class PlaybackTicketView(APIView):
    """Exchange an item id for a short-lived signed playback ticket.

    Teachers may preview their own item; students only if it is published and
    targeted at them.
    """
    permission_classes = [IsAuthenticated, IsEnvironmentMember]

    def post(self, request, pk):
        item = generics.get_object_or_404(
            ContentItem.objects.filter(environment=request.environment), pk=pk)
        if not item.video_file:
            raise serializers.ValidationError({"detail": "لا يوجد ملف فيديو مرفوع لهذا المحتوى."})

        if request.user.role == "student":
            if not _student_may_watch(item, _my_enrollment(request)):
                raise generics.Http404
        elif request.user.role != "teacher":
            raise generics.Http404

        # Optional `quality` ("720p" / 720): must name a rendition that really
        # exists for THIS item, otherwise 400 — never a silent fallback.
        height = None
        raw = request.data.get("quality") if hasattr(request.data, "get") else None
        if raw not in (None, "", "auto"):
            m = _QUALITY_RE.match(str(raw))
            if not m or not item.renditions.filter(height=int(m.group(1))).exists():
                raise serializers.ValidationError({"quality": "جودة غير متاحة لهذا الفيديو."})
            height = int(m.group(1))

        return Response({
            "ticket": issue_ticket(item.id, request.user.id, height),
            "expires_in": getattr(settings, "VIDEO_PLAYBACK_TTL_SECONDS", 300),
            "qualities": [{"label": r.label, "height": r.height} for r in item.renditions.all()],
        })


class VideoStreamView(APIView):
    """Stream the bytes for a valid ticket — after re-checking authorisation.

    The signed ticket IS the credential here: a `<video>` element cannot send
    an Authorization header, and making the player download the whole file
    through fetch() just to add one defeats seeking, instant start and speed
    control. The ticket is unforgeable, expires in minutes, names the viewer,
    and every request still re-checks that viewer's live authorisation — so a
    copied URL stops working the moment access is revoked or it expires.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        item_id, viewer_id, height = resolve_ticket_full(request.query_params.get("t"))
        item = generics.get_object_or_404(ContentItem.objects.all(), pk=item_id)
        viewer = generics.get_object_or_404(User.objects.filter(is_active=True), pk=viewer_id)

        if viewer.role == "student":
            enrollment = Enrollment.objects.filter(
                environment=item.environment, student=viewer, is_active=True).first()
            if enrollment is None or not _student_may_watch(item, enrollment):
                raise Http404
        elif viewer.role == "teacher":
            # Only the teacher who owns the environment may preview it.
            if not item.environment.memberships.filter(user=viewer, role="owner").exists():
                raise Http404
        else:
            raise Http404
        if height:
            rendition = item.renditions.filter(height=height).first()
            if rendition is None:
                raise Http404
            return stream_file(item, request, field=rendition.video_file, content_type="video/mp4")
        return stream_file(item, request)


class ProgressSerializer(serializers.Serializer):
    position_seconds = serializers.IntegerField(min_value=0, max_value=60 * 60 * 24)
    duration_seconds = serializers.IntegerField(min_value=0, max_value=60 * 60 * 24, required=False, default=0)


class VideoProgressView(APIView):
    """A student records their own viewing position. There is no enrollment id
    in the payload: it is derived from the authenticated user, so one student
    cannot write progress onto another's record."""
    permission_classes = IS_STUDENT

    def put(self, request, pk):
        item = generics.get_object_or_404(
            ContentItem.objects.filter(environment=request.environment), pk=pk)
        enrollment = _my_enrollment(request)
        if not _student_may_watch(item, enrollment):
            raise generics.Http404
        ser = ProgressSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        row, _ = VideoProgress.objects.get_or_create(
            item=item, enrollment=enrollment,
            defaults={"environment": request.environment})
        row.apply(ser.validated_data["position_seconds"], ser.validated_data.get("duration_seconds", 0))
        row.save()
        return Response({
            "item_id": item.id, "position_seconds": row.position_seconds,
            "duration_seconds": row.duration_seconds, "percent": row.percent,
            "completed": row.completed, "last_watched_at": row.last_watched_at,
        })


class ItemProgressView(APIView):
    """Teacher view of who watched an item and how far."""
    permission_classes = IS_ENV_OWNER

    def get(self, request, pk):
        item = _owned_item(request, pk)
        rows = (VideoProgress.objects.filter(item=item)
                .select_related("enrollment", "enrollment__student"))
        return Response({"results": [{
            "enrollment_id": r.enrollment_id,
            "name": r.enrollment.display_name,
            "percent": r.percent,
            "completed": r.completed,
            "position_seconds": r.position_seconds,
            "last_watched_at": r.last_watched_at,
        } for r in rows]})
