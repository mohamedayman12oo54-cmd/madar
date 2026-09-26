from django.urls import path

from . import views

urlpatterns = [
    path("grades/", views.GradeListCreateView.as_view()),
    path("grades/<int:pk>/", views.GradeDetailView.as_view()),
    path("groups/", views.GroupListCreateView.as_view()),
    path("groups/<int:pk>/", views.GroupDetailView.as_view()),
    path("enrollments/", views.EnrollmentListCreateView.as_view()),
    path("enrollments/<int:pk>/", views.EnrollmentDetailView.as_view()),
]
