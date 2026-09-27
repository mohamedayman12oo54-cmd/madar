from django.urls import path

from . import views

urlpatterns = [
    path("notes/", views.TeacherNoteListCreateView.as_view()),
    path("notes/<int:pk>/", views.TeacherNoteDetailView.as_view()),
    path("ratings/", views.RatingListCreateView.as_view()),
    path("ratings/<int:pk>/", views.RatingDetailView.as_view()),
]
