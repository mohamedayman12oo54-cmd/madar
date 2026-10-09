from django.urls import path

from . import views

urlpatterns = [
    path("request/", views.GuardianRequestView.as_view()),
    path("verify/", views.GuardianVerifyView.as_view()),
    path("overview/", views.GuardianOverviewView.as_view()),
]
