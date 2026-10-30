from django.urls import path

from . import registration, views

urlpatterns = [
    path("grades/", views.GradeListCreateView.as_view()),
    path("grades/<int:pk>/", views.GradeDetailView.as_view()),
    path("groups/", views.GroupListCreateView.as_view()),
    path("groups/<int:pk>/", views.GroupDetailView.as_view()),
    path("enrollments/", views.EnrollmentListCreateView.as_view()),
    path("enrollments/<int:pk>/", views.EnrollmentDetailView.as_view()),
    path("registration-link/", registration.RegistrationLinkView.as_view()),
    path("register/<str:token>/", registration.RegistrationInfoView.as_view()),
    path("register/<str:token>/submit/", registration.RegistrationSubmitView.as_view()),
]
