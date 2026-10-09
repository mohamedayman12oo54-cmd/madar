"""
Resumable video upload (TUS-shaped).

    POST  /content/<item>/uploads/   -> create a session, get its URL
    HEAD  /content/uploads/<id>/     -> where did I get to?  (Upload-Offset)
    PATCH /content/uploads/<id>/     -> send the next chunk from that offset
    DELETE/content/uploads/<id>/     -> abandon it

Why offsets rather than one big POST: a 2 GB upload that dies at 95% must
resume, not restart. The server is the authority on the offset — the client
asks, it never asserts — so a confused or malicious client cannot make the
file skip or overlap bytes.

Every limit is enforced before bytes are written (declared size, content type,
per-teacher concurrency) and again as they arrive (the real total can never
exceed what was declared). The finished file goes through exactly the same
magic-byte validation as a single-shot upload, because a chunked upload is
just as capable of carrying an executable.
"""
import os
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils import timezone
from rest_framework import generics, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeacher
from environments.tenancy import IsEnvironmentMember

from .models import ContentItem, UploadSession
from .providers import get_provider
from .uploads import (ALLOWED_CONTENT_TYPES, ALLOWED_EXTENSIONS, safe_display_name,
                      storage_path, validate_video_upload)
from .video_views import VideoUploadRateThrottle

IS_ENV_OWNER = [IsTeacher, IsEnvironmentMember.for_role("owner")]
SESSION_TTL_HOURS = 24
MAX_CHUNK_BYTES = 16 * 1024 * 1024
MAX_ACTIVE_SESSIONS = 5


def _session_for(request, pk):
    """Sessions resolve only inside the caller's environment AND only for the
    teacher who started them."""
    return generics.get_object_or_404(
        UploadSession.objects.select_related("item"),
        pk=pk, environment=request.environment, created_by=request.user,
    )


class CreateSessionSerializer(serializers.Serializer):
    filename = serializers.CharField(max_length=200)
    total_bytes = serializers.IntegerField(min_value=1)
    content_type = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")

    def validate_total_bytes(self, value):
        cap = getattr(settings, "VIDEO_MAX_BYTES", 512 * 1024 * 1024)
        if value > cap:
            raise serializers.ValidationError(
                f"حجم الفيديو يتجاوز الحد المسموح ({cap // (1024 * 1024)} ميجابايت)."
            )
        return value

    def validate_filename(self, value):
        ext = os.path.splitext(value or "")[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError("صيغة غير مدعومة. الصيغ المسموحة: MP4, M4V, WEBM, MOV.")
        return value

    def validate_content_type(self, value):
        value = (value or "").split(";")[0].strip().lower()
        if value and value not in ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError("نوع الملف غير مدعوم.")
        return value


class UploadSessionCreateView(APIView):
    """Authorise an upload and hand back where to send the bytes."""

    permission_classes = IS_ENV_OWNER
    throttle_classes = [VideoUploadRateThrottle]

    def post(self, request, pk):
        item = generics.get_object_or_404(
            ContentItem.objects.filter(environment=request.environment), pk=pk)
        ser = CreateSessionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        active = UploadSession.objects.filter(
            created_by=request.user, status=UploadSession.Status.ACTIVE,
            expires_at__gt=timezone.now()).count()
        if active >= MAX_ACTIVE_SESSIONS:
            raise serializers.ValidationError(
                {"detail": "لديك عمليات رفع جارية كثيرة. أكملها أو ألغها أولًا."})

        session = UploadSession.objects.create(
            environment=request.environment,
            item=item,
            created_by=request.user,
            filename=safe_display_name(ser.validated_data["filename"]),
            content_type=ser.validated_data["content_type"],
            total_bytes=ser.validated_data["total_bytes"],
            expires_at=timezone.now() + timedelta(hours=SESSION_TTL_HOURS),
        )
        ContentItem.objects.filter(pk=item.pk).update(
            processing_status=ContentItem.Processing.UPLOADING, processing_error="")

        target = get_provider().direct_upload(session)
        return Response({
            "id": str(session.id),
            "upload_url": target.upload_url,
            "method": target.method,
            "resumable": target.resumable,
            "offset": session.offset,
            "total_bytes": session.total_bytes,
            "max_chunk_bytes": MAX_CHUNK_BYTES,
            "expires_at": session.expires_at,
        }, status=status.HTTP_201_CREATED)


class UploadSessionView(APIView):
    """HEAD = where am I; PATCH = continue; DELETE = abandon."""

    permission_classes = IS_ENV_OWNER
    throttle_classes = [VideoUploadRateThrottle]

    def _headers(self, response, session):
        response["Upload-Offset"] = str(session.offset)
        response["Upload-Length"] = str(session.total_bytes)
        response["Cache-Control"] = "no-store"
        return response

    def head(self, request, pk):
        session = _session_for(request, pk)
        return self._headers(Response(status=status.HTTP_200_OK), session)

    def get(self, request, pk):
        """Same answer as HEAD, in a body — browsers make HEAD awkward to read."""
        session = _session_for(request, pk)
        return self._headers(Response({
            "id": str(session.id), "offset": session.offset,
            "total_bytes": session.total_bytes, "status": session.status,
            "is_complete": session.is_complete, "expires_at": session.expires_at,
        }), session)

    def patch(self, request, pk):
        session = _session_for(request, pk)

        if session.status != UploadSession.Status.ACTIVE:
            raise serializers.ValidationError({"detail": "عملية الرفع لم تعد نشطة."})
        if session.is_expired:
            UploadSession.objects.filter(pk=session.pk).update(status=UploadSession.Status.EXPIRED)
            raise serializers.ValidationError({"detail": "انتهت صلاحية عملية الرفع. ابدأ من جديد."})

        # The client must say which offset it believes it is at; a mismatch
        # means the two sides disagree and continuing would corrupt the file.
        declared = request.META.get("HTTP_UPLOAD_OFFSET")
        if declared is None:
            raise serializers.ValidationError({"detail": "ترويسة Upload-Offset مطلوبة."})
        try:
            declared = int(declared)
        except (TypeError, ValueError):
            raise serializers.ValidationError({"detail": "قيمة Upload-Offset غير صالحة."})
        if declared != session.offset:
            return self._headers(
                Response({"detail": "موضع الرفع غير متطابق.", "offset": session.offset},
                         status=status.HTTP_409_CONFLICT), session)

        chunk = request.body or b""
        if not chunk:
            raise serializers.ValidationError({"detail": "لم تصل أي بيانات."})
        if len(chunk) > MAX_CHUNK_BYTES:
            raise serializers.ValidationError({"detail": "حجم الجزء أكبر من المسموح."})
        if session.offset + len(chunk) > session.total_bytes:
            raise serializers.ValidationError(
                {"detail": "البيانات تتجاوز الحجم المعلن لعملية الرفع."})

        path = session.storage_path or storage_path(session, session.filename)
        full = os.path.join(settings.MEDIA_ROOT, path)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "ab") as fh:
            fh.write(chunk)

        with transaction.atomic():
            locked = UploadSession.objects.select_for_update().get(pk=session.pk)
            locked.storage_path = path
            locked.offset = os.path.getsize(full)
            locked.save(update_fields=["storage_path", "offset", "updated_at"])
            session = locked

        if session.is_complete:
            return self._finish(session)
        return self._headers(Response({"offset": session.offset, "is_complete": False}), session)

    def _finish(self, session):
        """All bytes in: validate the assembled file, then attach or reject.

        Validation happens HERE, not per chunk, because a container's magic
        bytes only mean anything once the file is whole — and a chunked upload
        can smuggle an executable just as easily as a single POST.
        """
        full = os.path.join(settings.MEDIA_ROOT, session.storage_path)
        item = session.item
        try:
            with open(full, "rb") as fh:
                uploaded = ContentFile(b"", name=session.filename)
                uploaded.file = fh
                uploaded.size = os.path.getsize(full)
                uploaded.content_type = session.content_type
                validate_video_upload(uploaded)
        except DjangoValidationError as exc:
            os.remove(full)
            UploadSession.objects.filter(pk=session.pk).update(
                status=UploadSession.Status.ABORTED, error="; ".join(exc.messages))
            ContentItem.objects.filter(pk=item.pk).update(
                processing_status=ContentItem.Processing.FAILED,
                processing_error="; ".join(exc.messages))
            raise serializers.ValidationError({"video": list(exc.messages)})

        old = item.video_file.name if item.video_file else None
        ContentItem.objects.filter(pk=item.pk).update(
            video_file=session.storage_path,
            source=ContentItem.Source.UPLOAD,
            original_filename=session.filename,
            file_size=session.offset,
            content_type=session.content_type,
            video_provider="none",
            video_ref="",
            # One rendition, served by Madar: nothing left to transcode, so the
            # item is immediately playable. A transcoding provider would leave
            # this at PROCESSING until its webhook arrives.
            processing_status=ContentItem.Processing.READY,
            processing_error="",
            processed_at=timezone.now(),
        )
        UploadSession.objects.filter(pk=session.pk).update(status=UploadSession.Status.COMPLETED)
        if old and old != session.storage_path:
            item.video_file.storage.delete(old)

        session.refresh_from_db()
        return self._headers(Response({
            "offset": session.offset, "is_complete": True,
            "item_id": item.id, "processing_status": ContentItem.Processing.READY,
        }), session)

    def delete(self, request, pk):
        session = _session_for(request, pk)
        if session.storage_path:
            full = os.path.join(settings.MEDIA_ROOT, session.storage_path)
            if os.path.exists(full):
                os.remove(full)
        UploadSession.objects.filter(pk=session.pk).update(
            status=UploadSession.Status.ABORTED, offset=0, storage_path="")
        ContentItem.objects.filter(pk=session.item_id).update(
            processing_status=ContentItem.Processing.NONE)
        return Response(status=status.HTTP_204_NO_CONTENT)
