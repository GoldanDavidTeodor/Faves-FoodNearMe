from django.urls import path
from . import views

urlpatterns = [
    path("", views.feed, name="feed"),
    path("for-you/", views.for_you, name="for_you"),
    path("surprise/", views.surprise_me, name="surprise_me"),
    path("location-presets/", views.location_presets, name="location_presets"),
    path("tags/suggest/", views.tag_suggest, name="tag_suggest"),
    path("tags/popular/", views.tag_popular, name="tag_popular"),
    path("tags/hot/", views.tag_hot, name="tag_hot"),
    path("messages/", views.messages, name="messages"),
    path("messages/<str:username>/", views.messages, name="messages_thread"),
    path("posts/<int:post_id>/share/", views.post_share, name="post_share"),
    path("posts/<int:post_id>/report/", views.post_report, name="post_report"),
    path("posts/new/", views.post_create, name="post_create"),
    path("posts/<int:post_id>/like/", views.post_like, name="post_like"),
    path("comments/<int:comment_id>/like/", views.comment_like, name="comment_like"),
    path("posts/<int:post_id>/rate/", views.post_rate, name="post_rate"),
    path("posts/<int:post_id>/comment/", views.post_comment, name="post_comment"),
    path("profile/edit/", views.edit_profile, name="edit_profile"),
    path("user/<str:username>/", views.profile, name="profile"),
    path("user/<str:username>/follow/", views.toggle_follow, name="toggle_follow"),
]