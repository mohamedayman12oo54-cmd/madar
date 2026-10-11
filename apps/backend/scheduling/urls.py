from django.urls import path

from . import scanner, views

urlpatterns = [
    path("schedules/", views.ScheduleListCreateView.as_view()),
    path("schedules/<int:pk>/", views.ScheduleDetailView.as_view()),
    path("sessions/", views.SessionInstanceListCreateView.as_view()),
    path("sessions/bulk/", views.SessionBulkCreateView.as_view()),
    path("sessions/generate/", views.SessionGenerateView.as_view()),
    path("sessions/<int:pk>/", views.SessionInstanceDetailView.as_view()),
    path("sessions/<int:pk>/open/", views.SessionOpenView.as_view()),
    path("sessions/<int:pk>/close/", views.SessionCloseView.as_view()),
    path("sessions/<int:pk>/reopen/", views.SessionReopenView.as_view()),
    path("sessions/<int:pk>/roster/", views.SessionRosterView.as_view()),
    path("sessions/<int:pk>/guest-candidates/", views.GuestCandidatesView.as_view()),
    path("sessions/<int:pk>/guests/", views.GuestCreateView.as_view()),
    path("sessions/<int:pk>/guests/<int:enrollment_id>/", views.GuestDetailView.as_view()),
    path("attendance/mark/", views.MarkAttendanceView.as_view()),
    path("recitation/mark/", views.MarkRecitationView.as_view()),
    # --- teacher QR scanner ---
    path("scan/resolve/", scanner.ScanResolveView.as_view()),
    path("scan/attendance/", scanner.ScanAttendanceView.as_view()),
    path("scan/recitation/", scanner.ScanRecitationView.as_view()),
    path("scan/payment/", scanner.ScanPaymentView.as_view()),
    path("scan/badge/<int:enrollment_id>/rotate/", scanner.RotateBadgeView.as_view()),
]
