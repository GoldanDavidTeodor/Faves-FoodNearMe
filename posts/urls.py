from django.urls import path
from . import views

urlpatterns = [
    path("", views.feed, name="feed"),
    path("posts/new/", views.post_create, name="post_create"),
]