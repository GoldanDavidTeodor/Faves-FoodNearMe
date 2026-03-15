from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Comment, Like, Post, Rating

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


class PostRatingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="rater", password="pass12345")
        self.author = User.objects.create_user(username="chef", password="pass12345")
        self.post = Post.objects.create(user=self.author, title="Taco Spot")

    def test_rate_creates_then_updates_user_rating(self):
        self.client.login(username="rater", password="pass12345")
        rate_url = reverse("post_rate", args=[self.post.id])

        self.client.post(rate_url, {"next": reverse("feed"), "rating": "7"})
        self.assertEqual(Rating.objects.get(user=self.user, post=self.post).value, 7)

        self.client.post(rate_url, {"next": reverse("feed"), "rating": "10"})
        self.assertEqual(Rating.objects.get(user=self.user, post=self.post).value, 10)
        self.assertEqual(Rating.objects.filter(user=self.user, post=self.post).count(), 1)

    def test_rate_ignores_out_of_range_values(self):
        self.client.login(username="rater", password="pass12345")
        rate_url = reverse("post_rate", args=[self.post.id])

        self.client.post(rate_url, {"next": reverse("feed"), "rating": "11"})
        self.assertFalse(Rating.objects.filter(user=self.user, post=self.post).exists())

    def test_rate_route_rejects_get(self):
        self.client.login(username="rater", password="pass12345")
        rate_url = reverse("post_rate", args=[self.post.id])

        response = self.client.get(rate_url)

        self.assertEqual(response.status_code, 405)


class PostCommentTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="commenter", password="pass12345")
        self.author = User.objects.create_user(username="owner", password="pass12345")
        self.post = Post.objects.create(user=self.author, title="Burger Spot")

    def test_comment_is_created(self):
        self.client.login(username="commenter", password="pass12345")
        comment_url = reverse("post_comment", args=[self.post.id])

        self.client.post(comment_url, {"next": reverse("feed"), "text": "Looks great"})

        self.assertTrue(
            Comment.objects.filter(user=self.user, post=self.post, text="Looks great").exists()
        )

    def test_blank_comment_is_ignored(self):
        self.client.login(username="commenter", password="pass12345")
        comment_url = reverse("post_comment", args=[self.post.id])

        self.client.post(comment_url, {"next": reverse("feed"), "text": "   "})

        self.assertFalse(Comment.objects.filter(user=self.user, post=self.post).exists())

    def test_comment_route_rejects_get(self):
        self.client.login(username="commenter", password="pass12345")
        comment_url = reverse("post_comment", args=[self.post.id])

        response = self.client.get(comment_url)

        self.assertEqual(response.status_code, 405)

    def test_reply_comment_creates_subthread(self):
        self.client.login(username="commenter", password="pass12345")
        parent = Comment.objects.create(user=self.author, post=self.post, text="Top comment")
        comment_url = reverse("post_comment", args=[self.post.id])

        self.client.post(
            comment_url,
            {
                "next": reverse("feed"),
                "text": "Reply comment",
                "parent_id": str(parent.id),
            },
        )

        reply = Comment.objects.get(user=self.user, post=self.post, text="Reply comment")
        self.assertEqual(reply.parent_id, parent.id)
