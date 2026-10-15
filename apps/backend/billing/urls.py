"""
BILL-WU-031 — read endpoints only. Checkout (BILL-WU-019), cancellation
(BILL-WU-028) and the webhook (BILL-WU-020) mount into this same namespace
in later units — not present yet.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("plans/", views.PlanListView.as_view()),
    path("subscription/", views.SubscriptionStatusView.as_view()),
    path("history/", views.PaymentHistoryView.as_view()),
]
