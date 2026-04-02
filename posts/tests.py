from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Comment, Follow, Like, Message, Post, Rating

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


class MessagesTests(TestCase):
    def setUp(self):
        self.me = User.objects.create_user(username="me", password="pass12345")
        self.follower = User.objects.create_user(username="fan", password="pass12345")
        self.stranger = User.objects.create_user(username="stranger", password="pass12345")

        Follow.objects.create(follower=self.follower, following=self.me)

    def test_messages_page_requires_login(self):
        response = self.client.get(reverse("messages"))
        self.assertEqual(response.status_code, 302)

    def test_can_open_thread_with_follower(self):
        self.client.login(username="me", password="pass12345")
        response = self.client.get(reverse("messages_thread", args=["fan"]))
        self.assertEqual(response.status_code, 200)

    def test_cannot_open_thread_with_non_follower(self):
        self.client.login(username="me", password="pass12345")
        response = self.client.get(reverse("messages_thread", args=["stranger"]))
        self.assertEqual(response.status_code, 404)

    def test_post_message_creates_message(self):
        self.client.login(username="me", password="pass12345")
        url = reverse("messages_thread", args=["fan"]) 

        self.client.post(url, {"text": "hello"})

        self.assertTrue(
            Message.objects.filter(sender=self.me, recipient=self.follower, text="hello").exists()
        )


class SharePostTests(TestCase):
    def setUp(self):
        self.me = User.objects.create_user(username="me", password="pass12345")
        self.follower = User.objects.create_user(username="fan", password="pass12345")
        self.author = User.objects.create_user(username="author", password="pass12345")

        Follow.objects.create(follower=self.follower, following=self.me)
        self.post = Post.objects.create(user=self.author, title="Shared post")

    def test_share_post_creates_message_with_post(self):
        self.client.login(username="me", password="pass12345")
        url = reverse("post_share", args=[self.post.id])

        self.client.post(url, {"recipient": "fan"})

        self.assertTrue(
            Message.objects.filter(
                sender=self.me,
                recipient=self.follower,
                post=self.post,
                text="",
            ).exists()
        )
