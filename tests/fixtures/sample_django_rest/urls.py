"""Sample Django REST URLs for extractor tests."""

from django.urls import path

from .views import UserListView, health


urlpatterns = [
    path("health/", health),
    path("users/", UserListView.as_view()),
]
