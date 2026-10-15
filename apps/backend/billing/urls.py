"""
BILL-WU-031 — read endpoints. BILL-WU-019 adds checkout initiation and its
redirect-return landing. BILL-WU-020 adds the one inbound Kashier webhook.
Cancellation (BILL-WU-028) mounts into this same namespace in a later
unit — not present yet.
"""
from django.urls import path

from . import views
from .webhooks import KashierWebhookView

urlpatterns = [
    path("plans/", views.PlanListView.as_view()),
    path("subscription/", views.SubscriptionStatusView.as_view()),
    path("history/", views.PaymentHistoryView.as_view()),
    path("checkout/", views.CheckoutView.as_view()),
    path("checkout/return/", views.CheckoutReturnView.as_view()),
    path("webhooks/kashier/", KashierWebhookView.as_view()),
]
