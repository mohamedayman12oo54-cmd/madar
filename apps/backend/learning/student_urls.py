from django.urls import path

from . import student_views as s

urlpatterns = [
    path("", s.ExamListView.as_view()),
    path("<int:pk>/start/", s.ExamStartView.as_view()),
    path("<int:pk>/question/<int:index>/", s.ExamQuestionView.as_view()),
    path("<int:pk>/answer/", s.ExamAnswerView.as_view()),
    path("<int:pk>/violation/", s.ExamViolationView.as_view()),
    path("<int:pk>/submit/", s.ExamSubmitView.as_view()),
    path("<int:pk>/result/", s.ExamResultView.as_view()),
]
