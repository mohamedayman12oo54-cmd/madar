from django.urls import path

from . import views

urlpatterns = [
    path("monthly/", views.MonthlyEvaluationView.as_view()),
    path("ratings/", views.RatingUpsertView.as_view()),
    path("ratings/publish/", views.RatingPublishView.as_view()),
    path("ratings/publish-all/", views.RatingPublishAllView.as_view()),
    path("states/", views.StateUpsertView.as_view()),
    path("notes/", views.NoteListCreateView.as_view()),
    path("notes/<int:pk>/", views.NoteDetailView.as_view()),
]
