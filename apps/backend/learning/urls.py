from django.urls import path

from . import views as v

urlpatterns = [
    path("", v.ExamListCreateView.as_view()),
    path("<int:pk>/", v.ExamDetailView.as_view()),
    path("<int:pk>/publish/", v.ExamPublishView.as_view()),
    path("<int:pk>/results/", v.ExamResultsView.as_view()),
    path("<int:pk>/reopen/", v.ExamReopenView.as_view()),
]
