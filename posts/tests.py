from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Like, Post

User = get_user_model()


class PostLikeToggleTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="liker", password="pass12345")
        self.author = User.objects.create_user(username="author", password="pass12345")
        self.post = Post.objects.create(user=self.author, title="Pizza Spot")

    def test_like_then_unlike_toggles(self):
        self.client.login(username="liker", password="pass12345")
        like_url = reverse("post_like", args=[self.post.id])

        self.client.post(like_url, {"next": reverse("feed")})
        self.assertTrue(Like.objects.filter(user=self.user, post=self.post).exists())

        self.client.post(like_url, {"next": reverse("feed")})
        self.assertFalse(Like.objects.filter(user=self.user, post=self.post).exists())

    def test_like_route_rejects_get(self):
        self.client.login(username="liker", password="pass12345")
        like_url = reverse("post_like", args=[self.post.id])

        response = self.client.get(like_url)

        self.assertEqual(response.status_code, 405)
