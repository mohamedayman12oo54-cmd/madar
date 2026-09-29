from django.urls import path

from . import views

urlpatterns = [
    path("operations/", views.AIOperationListSubmitView.as_view()),
    path("operations/<int:pk>/", views.AIOperationDetailView.as_view()),
]
