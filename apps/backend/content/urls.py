from django.urls import path

from . import document_views, transcript_views, upload_views, video_views, views

urlpatterns = [
    path("", views.ContentListCreateView.as_view()),
    path("<int:pk>/", views.ContentDetailView.as_view()),
    path("<int:pk>/publish/", views.ContentPublishView.as_view()),
    # --- uploaded video: private storage, signed short-lived playback ---
    path("<int:pk>/video/", video_views.VideoUploadView.as_view()),
    path("<int:pk>/playback-ticket/", video_views.PlaybackTicketView.as_view()),
    path("<int:pk>/progress/", video_views.VideoProgressView.as_view()),
    path("<int:pk>/watchers/", video_views.ItemProgressView.as_view()),
    path("<int:pk>/transcript/", transcript_views.TranscriptView.as_view()),
    path("stream/", video_views.VideoStreamView.as_view()),
    # --- PDF study files: private storage, signed short-lived viewing ---
    path("<int:pk>/document/", document_views.DocumentUploadView.as_view()),
    path("<int:pk>/document-ticket/", document_views.DocumentTicketView.as_view()),
    path("document/", document_views.DocumentStreamView.as_view()),
    # --- resumable upload (create / resume / continue / abandon) ---
    path("<int:pk>/uploads/", upload_views.UploadSessionCreateView.as_view()),
    path("uploads/<uuid:pk>/", upload_views.UploadSessionView.as_view()),
]
