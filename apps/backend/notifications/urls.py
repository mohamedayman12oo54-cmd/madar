from django.urls import path

from . import views

urlpatterns = [
    path("", views.NotificationListView.as_view()),
    path("summary/", views.NotificationSummaryView.as_view()),
    path("broadcast/", views.BroadcastView.as_view()),
    path("broadcasts/", views.BroadcastLogView.as_view()),
    path("broadcasts/<int:pk>/", views.BroadcastDetailView.as_view()),
    path("retry-failed/", views.RetryFailedView.as_view()),
]
