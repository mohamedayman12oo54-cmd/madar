from django.urls import path

from . import views

urlpatterns = [
    path("login/", views.GuardianCodeLoginView.as_view()),
    path("request/", views.GuardianRequestView.as_view()),
    path("verify/", views.GuardianVerifyView.as_view()),
    path("renew/", views.GuardianRenewView.as_view()),
    path("overview/", views.GuardianOverviewView.as_view()),
    path("messages/<int:pk>/read/", views.GuardianMessageReadView.as_view()),
    path("messages/<int:pk>/reply/", views.GuardianReplyView.as_view()),
]
