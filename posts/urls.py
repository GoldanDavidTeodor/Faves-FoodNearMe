from django.urls import path
from . import views

urlpatterns = [
    path("", views.feed, name="feed"),
    path("for-you/", views.for_you, name="for_you"),
    path("posts/new/", views.post_create, name="post_create"),
    path("posts/<int:post_id>/like/", views.post_like, name="post_like"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("user/<str:username>/", views.profile, name="profile"),
    path("user/<str:username>/follow/", views.toggle_follow, name="toggle_follow"),
]