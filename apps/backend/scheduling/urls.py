from django.urls import path

from . import views

urlpatterns = [
    path("sessions/", views.SessionInstanceListCreateView.as_view()),
    path("sessions/<int:pk>/", views.SessionInstanceDetailView.as_view()),
    path("sessions/<int:pk>/open/", views.SessionOpenView.as_view()),
    path("sessions/<int:pk>/close/", views.SessionCloseView.as_view()),
    path("sessions/<int:pk>/reopen/", views.SessionReopenView.as_view()),
    path("attendance/", views.AttendanceListView.as_view()),
    path("attendance/<int:pk>/", views.AttendanceDetailView.as_view()),
]
