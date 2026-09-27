from django.urls import path

from . import views

urlpatterns = [
    path("payments/", views.PaymentListCreateView.as_view()),
    path("payments/<int:pk>/", views.PaymentDetailView.as_view()),
    path("summary/", views.FinancialSummaryView.as_view()),
]
