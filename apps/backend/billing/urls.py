"""
BILL-WU-031 — read endpoints. BILL-WU-019 adds checkout initiation and its
redirect-return landing. Cancellation (BILL-WU-028) and the webhook
(BILL-WU-020) mount into this same namespace in later units — not present
yet.
"""
from django.urls import path

from . import views

urlpatterns = [
    path("plans/", views.PlanListView.as_view()),
    path("subscription/", views.SubscriptionStatusView.as_view()),
    path("history/", views.PaymentHistoryView.as_view()),
    path("checkout/", views.CheckoutView.as_view()),
    path("checkout/return/", views.CheckoutReturnView.as_view()),
]
