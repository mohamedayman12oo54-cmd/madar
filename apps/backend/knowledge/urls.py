from django.urls import path

from . import views

urlpatterns = [
    path("documents/", views.KBDocumentListCreateView.as_view()),
    path("documents/<int:pk>/", views.KBDocumentDetailView.as_view()),
    path("documents/<int:pk>/publish/", views.KBPublishView.as_view()),
    path("documents/<int:pk>/unpublish/", views.KBUnpublishView.as_view()),
]
