from django.urls import path

from . import views as v

urlpatterns = [
    path("overview/", v.OverviewView.as_view()),
    path("attendance/", v.AttendanceView.as_view()),
    path("recitation/", v.RecitationView.as_view()),
    path("payments/", v.PaymentsView.as_view()),
    path("evaluation/", v.EvaluationView.as_view()),
    path("videos/", v.VideoListView.as_view()),
    path("videos/<int:pk>/", v.VideoDetailView.as_view()),
    path("materials/", v.MaterialListView.as_view()),
    path("materials/<int:pk>/", v.MaterialDetailView.as_view()),
    path("notifications/", v.NotificationListView.as_view()),
    path("notifications/read-all/", v.NotificationReadAllView.as_view()),
    path("notifications/<int:pk>/read/", v.NotificationReadView.as_view()),
    path("quizzes/", v.QuizListRequestView.as_view()),
    path("quizzes/operations/<int:pk>/", v.QuizOperationView.as_view()),
    path("quizzes/<int:pk>/", v.QuizDetailView.as_view()),
    path("quizzes/<int:pk>/submit/", v.QuizSubmitView.as_view()),
    path("assistant/", v.AssistantListSubmitView.as_view()),
    path("assistant/<int:pk>/", v.AssistantDetailView.as_view()),
]
