"""
Content Maintainer authoring surface for the central Knowledge Base.

Authorization (docs: glossary — "the internal Madar operator who curates the
Knowledge Base. Has no access to teacher educational records"): every view
here requires role=team. There is deliberately NO teacher or student write
path, and nothing in this app is tenant-scoped, because the KB is central and
product-owned. Teachers do not curate AI sources in V1.
"""
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsTeam

from .models import KBDocument
from .serializers import KBDocumentSerializer

IS_MAINTAINER = [IsTeam]


class KBDocumentListCreateView(generics.ListCreateAPIView):
    permission_classes = IS_MAINTAINER
    serializer_class = KBDocumentSerializer
    queryset = KBDocument.objects.all()

    def get_queryset(self):
        qs = super().get_queryset()
        if status_filter := self.request.query_params.get("status"):
            qs = qs.filter(status=status_filter)
        if search := self.request.query_params.get("search", "").strip():
            qs = qs.filter(title__icontains=search)
        return qs

    def perform_create(self, serializer):
        # New curation always starts as a draft: only published content is
        # authoritative for AI consumption.
        serializer.save(created_by=self.request.user, status=KBDocument.Status.DRAFT)


class KBDocumentDetailView(generics.RetrieveUpdateDestroyAPIView):
    permission_classes = IS_MAINTAINER
    serializer_class = KBDocumentSerializer
    queryset = KBDocument.objects.all()


class KBPublishView(APIView):
    permission_classes = IS_MAINTAINER

    def post(self, request, pk):
        doc = generics.get_object_or_404(KBDocument.objects.all(), pk=pk)
        doc.publish()
        return Response(KBDocumentSerializer(doc).data)


class KBUnpublishView(APIView):
    permission_classes = IS_MAINTAINER

    def post(self, request, pk):
        doc = generics.get_object_or_404(KBDocument.objects.all(), pk=pk)
        doc.unpublish()
        return Response(KBDocumentSerializer(doc).data)
