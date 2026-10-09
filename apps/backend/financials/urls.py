from django.urls import path

from . import views

urlpatterns = [
    path("monthly/", views.MonthlyPaymentsView.as_view()),
    path("enrollments/<int:enrollment_id>/history/", views.PaymentHistoryView.as_view()),
]
