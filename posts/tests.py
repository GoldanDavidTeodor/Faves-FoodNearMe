from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .models import Comment, Follow, Like, Message, Post, PostReport, Rating, Tag

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


class PostCreateTagsTests(TestCase):
    def setUp(self):
        self.author = User.objects.create_user(username="author", password="pass12345")

    def test_create_post_with_tags_creates_and_links_tags(self):
        self.client.login(username="author", password="pass12345")
        url = reverse("post_create")

        response = self.client.post(url, {
            "title": "Lemonade",
            "tags": "sweet, sour, cold",
        })

        self.assertEqual(response.status_code, 302)
        post = Post.objects.get(title="Lemonade")
        self.assertEqual(set(post.tags.values_list("name", flat=True)), {"sweet", "sour", "cold"})
        self.assertTrue(Tag.objects.filter(name="sweet").exists())


class PostReportTests(TestCase):
    def setUp(self):
        self.reporter = User.objects.create_user(username="reporter", password="pass12345")
        self.author = User.objects.create_user(username="author", password="pass12345")
        self.post = Post.objects.create(user=self.author, title="Spam post")

    def test_report_post_creates_report(self):
        self.client.login(username="reporter", password="pass12345")
        url = reverse("post_report", args=[self.post.id])

        response = self.client.post(url, {"next": reverse("feed")})

        self.assertEqual(response.status_code, 302)
        self.assertTrue(PostReport.objects.filter(post=self.post, reporter=self.reporter).exists())

    def test_report_route_rejects_get(self):
        self.client.login(username="reporter", password="pass12345")
        url = reverse("post_report", args=[self.post.id])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 405)


class ProfileForwardsCountTests(TestCase):
    def setUp(self):
        self.profile_user = User.objects.create_user(username="author", password="pass12345")
        self.sender = User.objects.create_user(username="sender", password="pass12345")
        self.recipient = User.objects.create_user(username="recipient", password="pass12345")

        self.post = Post.objects.create(user=self.profile_user, title="Wings")

    def test_profile_posts_are_annotated_with_forwards_count(self):
        Message.objects.create(sender=self.sender, recipient=self.recipient, post=self.post, text="")
        Message.objects.create(sender=self.sender, recipient=self.recipient, post=self.post, text="")
        Message.objects.create(sender=self.sender, recipient=self.recipient, post=self.post, text="")

        response = self.client.get(reverse("profile", args=[self.profile_user.username]))

        self.assertEqual(response.status_code, 200)
        user_posts = list(response.context["user_posts"])
        self.assertEqual(len(user_posts), 1)
        self.assertEqual(user_posts[0].forwards_count, 3)


class ForYouRankingTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(username="viewer", password="pass12345")
        self.author_a = User.objects.create_user(username="author_a", password="pass12345")
        self.author_b = User.objects.create_user(username="author_b", password="pass12345")

        self.tag_pizza = Tag.objects.create(name="pizza")
        self.tag_sushi = Tag.objects.create(name="sushi")

        self.post_pizza = Post.objects.create(user=self.author_a, title="Pizza place")
        self.post_pizza.tags.add(self.tag_pizza)

        self.post_sushi = Post.objects.create(user=self.author_b, title="Sushi place")
        self.post_sushi.tags.add(self.tag_sushi)

    def test_followed_author_gets_boost(self):
        Follow.objects.create(follower=self.viewer, following=self.author_b)
        self.client.login(username="viewer", password="pass12345")

        response = self.client.get(reverse("for_you"))
        self.assertEqual(response.status_code, 200)

        posts = list(response.context["posts"])
        self.assertTrue(posts)
        self.assertEqual(posts[0].id, self.post_sushi.id)

    def test_high_rated_tag_is_ranked_higher(self):
        Rating.objects.create(user=self.viewer, post=self.post_pizza, value=10)
        self.client.login(username="viewer", password="pass12345")

        response = self.client.get(reverse("for_you"))
        self.assertEqual(response.status_code, 200)

        posts = list(response.context["posts"])
        self.assertTrue(posts)
        self.assertEqual(posts[0].id, self.post_pizza.id)

    def test_user_low_rating_suppresses_post(self):
        # The user personally disliked the sushi post; it should not surface as #1.
        Rating.objects.create(user=self.viewer, post=self.post_sushi, value=1)
        self.client.login(username="viewer", password="pass12345")

        response = self.client.get(reverse("for_you"))
        self.assertEqual(response.status_code, 200)

        posts = list(response.context["posts"])
        self.assertTrue(posts)
        self.assertNotEqual(posts[0].id, self.post_sushi.id)
