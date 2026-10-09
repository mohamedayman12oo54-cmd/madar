from django.urls import path

from . import views

urlpatterns = [
    path("teacher/", views.TeacherEnvironmentListView.as_view()),
    path("teacher/<int:pk>/enter/", views.TeacherEnvironmentEnterView.as_view()),
    path("student/", views.StudentEnvironmentListView.as_view()),
    path("student/<int:pk>/enter/", views.StudentEnvironmentEnterView.as_view()),
    path("context/", views.EnvironmentContextView.as_view()),
    path("current/", views.EnvironmentSettingsView.as_view()),
    path("overview/", views.OverviewView.as_view()),
]
