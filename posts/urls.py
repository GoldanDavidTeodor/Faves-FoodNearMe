from django.urls import path
from . import views

urlpatterns = [
    path("", views.feed, name="feed"),
    path("posts/new/", views.post_create, name="post_create"),
    path("posts/<int:post_id>/like/", views.post_like, name="post_like"),
    path("user/<str:username>/", views.profile, name="profile"),
    path("user/<str:username>/follow/", views.toggle_follow, name="toggle_follow"),
]