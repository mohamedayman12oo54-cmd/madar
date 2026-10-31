"""
PDF study files (teacher upload + protected viewing for teacher and student).

Same security model as video, deliberately:
  * private storage — no public URL, random stored name, the client filename never touches disk;
  * validation beats the client — extension, declared type AND the file's own leading bytes;
  * viewing goes through a signed, short-lived ticket that names ONE item and ONE viewer, with its
    OWN salt (a video ticket cannot open a document or the other way round);
  * authorisation is re-checked on every request, so unpublishing / un-targeting / deactivating the
    enrolment / deleting the file kills an unexpired ticket immediately.
"""
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.http import Http404
from rest_framework import generics, serializers, status
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from academics.models import Enrollment
from accounts.models import User
from environments.tenancy import IsEnvironmentMember

from .models import ContentItem
from .streaming import DOCUMENT_SALT, issue_ticket, resolve_ticket_full, stream_file
from .uploads import safe_display_name, validate_document_upload
from .video_views import IS_ENV_OWNER, VideoUploadRateThrottle, _my_enrollment, _owned_item, _student_may_watch


def _pdf_item(request, pk):
    item = _owned_item(request, pk)
    if item.kind != ContentItem.Kind.PDF:
        raise serializers.ValidationError({"detail": "هذا المحتوى ليس ملف PDF."})
    return item


class DocumentUploadView(APIView):
    """PUT a PDF onto an existing PDF item (teacher only). Replacing deletes the previous blob."""

    permission_classes = IS_ENV_OWNER
    parser_classes = [MultiPartParser, FormParser]
    throttle_classes = [VideoUploadRateThrottle]

    def put(self, request, pk):
        item = _pdf_item(request, pk)
        upload = request.FILES.get("file")
        try:
            validate_document_upload(upload)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({"file": list(exc.messages)})

        old = item.document_file.name if item.document_file else None
        with transaction.atomic():
            item.document_file = upload
            item.source = ContentItem.Source.UPLOAD
            item.original_filename = safe_display_name(upload.name)
            item.file_size = upload.size
            item.content_type = "application/pdf"
            item.save()
        if old and old != item.document_file.name:
            item.document_file.storage.delete(old)
        return Response({
            "id": item.id, "original_filename": item.original_filename,
            "file_size": item.file_size, "has_document": True,
        })

    def delete(self, request, pk):
        """Remove the stored file; the item survives as a draft (a published PDF without a file would
        be an empty promise, so it is also taken back to draft)."""
        item = _pdf_item(request, pk)
        if item.document_file:
            item.document_file.delete(save=False)
        item.document_file = None
        item.original_filename = ""
        item.file_size = None
        item.content_type = ""
        item.source = ContentItem.Source.EXTERNAL
        item.published_at = None
        item.save()
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentTicketView(APIView):
    """Exchange an item id for a short-lived signed viewing ticket. Teachers may preview their own
    item; students only if it is published and targeted at them."""

    permission_classes = [IsAuthenticated, IsEnvironmentMember]

    def post(self, request, pk):
        item = generics.get_object_or_404(
            ContentItem.objects.filter(environment=request.environment, kind=ContentItem.Kind.PDF), pk=pk)
        if not item.document_file:
            raise serializers.ValidationError({"detail": "لا يوجد ملف مرفوع لهذا المحتوى."})
        if request.user.role == "student":
            if not _student_may_watch(item, _my_enrollment(request)):
                raise Http404
        elif request.user.role != "teacher":
            raise Http404
        return Response({
            "ticket": issue_ticket(item.id, request.user.id, salt=DOCUMENT_SALT),
            "expires_in": getattr(settings, "VIDEO_PLAYBACK_TTL_SECONDS", 300),
        })


class DocumentStreamView(APIView):
    """Serve the PDF for a valid ticket, after re-checking the named viewer's live authorisation.
    A browser tab cannot send an Authorization header, so (like video) the ticket is the credential:
    unforgeable, one item, one viewer, minutes of life."""

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        item_id, viewer_id, _ = resolve_ticket_full(request.query_params.get("t"), salt=DOCUMENT_SALT)
        item = generics.get_object_or_404(ContentItem.objects.filter(kind=ContentItem.Kind.PDF), pk=item_id)
        viewer = generics.get_object_or_404(User.objects.filter(is_active=True), pk=viewer_id)
        if viewer.role == "student":
            enrollment = Enrollment.objects.filter(
                environment=item.environment, student=viewer, is_active=True).first()
            if enrollment is None or not _student_may_watch(item, enrollment):
                raise Http404
        elif viewer.role == "teacher":
            if not item.environment.memberships.filter(user=viewer, role="owner").exists():
                raise Http404
        else:
            raise Http404
        response = stream_file(item, request, field=item.document_file, content_type="application/pdf")
        # Deliberately NOT a download: it opens in the viewer. The body is a PDF, never HTML.
        response["Content-Disposition"] = "inline"
        return response
