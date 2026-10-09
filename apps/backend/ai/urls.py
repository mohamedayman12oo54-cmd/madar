from django.urls import path

from . import views

urlpatterns = [
    path("state-recommendations/", views.StateRecommendationSubmitView.as_view()),
    path("operations/", views.AIOperationListSubmitView.as_view()),
    path("operations/<int:pk>/", views.AIOperationDetailView.as_view()),
]
