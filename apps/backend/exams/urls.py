from django.urls import path

from . import student_views as s
from . import views as t

urlpatterns = [
    # --- teacher ---
    path("", t.ExamListCreateView.as_view()),
    path("<int:pk>/", t.ExamDetailView.as_view()),
    path("<int:pk>/publish/", t.ExamPublishView.as_view()),
    path("<int:pk>/results/", t.ExamResultsView.as_view()),
    path("<int:pk>/attempts/<int:attempt_id>/", t.ExamAttemptView.as_view()),
    # --- student (the literal prefix keeps these apart from the teacher ids above) ---
    path("student/", s.ExamListView.as_view()),
    path("student/<int:pk>/", s.ExamDetailView.as_view()),
    path("student/<int:pk>/start/", s.ExamStartView.as_view()),
    path("student/<int:pk>/answer/", s.ExamAnswerView.as_view()),
    path("student/<int:pk>/events/", s.ExamEventView.as_view()),
    path("student/<int:pk>/submit/", s.ExamSubmitView.as_view()),
    path("student/<int:pk>/result/", s.ExamResultView.as_view()),
]
