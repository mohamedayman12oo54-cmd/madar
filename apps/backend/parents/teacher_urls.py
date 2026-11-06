from django.urls import path

from . import teacher_views

urlpatterns = [
    path("", teacher_views.GuardianMessageView.as_view()),
    path("unread/", teacher_views.UnreadRepliesView.as_view()),
    path("read-replies/", teacher_views.ReadRepliesView.as_view()),
    path("settings/", teacher_views.GuardianAlertSettingsView.as_view()),
]
