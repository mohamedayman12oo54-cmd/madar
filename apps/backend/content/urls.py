from django.urls import path

from . import views

urlpatterns = [
    path("", views.ContentListCreateView.as_view()),
    path("<int:pk>/", views.ContentDetailView.as_view()),
]
