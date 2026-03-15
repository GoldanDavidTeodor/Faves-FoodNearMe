from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Avg, Count, Prefetch
from django.http import JsonResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from .models import Comment, CommentLike, Follow, Like, Post, PostImage, Profile, Rating
from .forms import PostForm, ProfileForm

User = get_user_model()


COMMENT_PREFETCH = Prefetch(
    "comments",
    queryset=Comment.objects.select_related("user", "user__profile").annotate(
        likes_count=Count("likes", distinct=True)
    ),
)


def _wants_json(request):
    return request.headers.get("x-requested-with") == "XMLHttpRequest"


def _attach_current_user_ratings(posts, user):
    post_ids = [post.id for post in posts]
    ratings_map = {}
    if user.is_authenticated and post_ids:
        ratings_map = dict(
            Rating.objects.filter(user=user, post_id__in=post_ids)
            .values_list("post_id", "value")
        )

    for post in posts:
        post.current_user_rating = ratings_map.get(post.id)


def _attach_comment_threads(posts):
    for post in posts:
        all_comments = list(post.comments.all())
        top_level = []
        by_parent = {}

        for comment in all_comments:
            if comment.parent_id is None:
                top_level.append(comment)
            else:
                by_parent.setdefault(comment.parent_id, []).append(comment)

        for comment in top_level:
            comment.thread_replies = by_parent.get(comment.id, [])

        post.top_level_comments = top_level


def _attach_current_user_comment_likes(posts, user):
    liked_comment_ids = set()
    comment_ids = {
        comment.id
        for post in posts
        for comment in post.comments.all()
    }

    if user.is_authenticated and comment_ids:
        liked_comment_ids = set(
            CommentLike.objects.filter(user=user, comment_id__in=comment_ids)
            .values_list("comment_id", flat=True)
        )

    for post in posts:
        for comment in post.comments.all():
            comment.current_user_liked = comment.id in liked_comment_ids


def feed(request):
    posts = (
        Post.objects.select_related("user", "user__profile")
        .prefetch_related("images", COMMENT_PREFETCH)
        .annotate(
            avg_rating=Avg("ratings__value"),
            ratings_count=Count("ratings", distinct=True),
            comments_count=Count("comments", distinct=True),
        )
        .all()[:50]
    )

    # Build a set of post IDs the current user has liked
    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(
            Like.objects.filter(user=request.user, post__in=posts)
            .values_list("post_id", flat=True)
        )

    _attach_current_user_ratings(posts, request.user)
    _attach_current_user_comment_likes(posts, request.user)
    _attach_comment_threads(posts)

    return render(request, "posts/feed.html", {
        "posts": posts,
        "liked_ids": liked_ids,
    })


def for_you(request):
    return render(request, "posts/for_you.html")


@login_required
def post_create(request):
    if request.method == "POST":
        form = PostForm(request.POST, request.FILES)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.save()
            for img in request.FILES.getlist("images"):
                PostImage.objects.create(post=post, image=img)
            return redirect("feed")
    else:
        form = PostForm()

    return render(request, "posts/post_form.html", {"form": form})


@login_required
@require_POST
def post_like(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    existing_likes = Like.objects.filter(user=request.user, post=post)
    liked = True
    if existing_likes.exists():
        existing_likes.delete()
        liked = False
    else:
        Like.objects.create(user=request.user, post=post)

    if _wants_json(request):
        return JsonResponse({
            "post_id": post.id,
            "liked": liked,
            "likes_count": post.likes.count(),
        })

    next_url = request.POST.get("next", "feed")
    return redirect(next_url)


@login_required
@require_POST
def post_rate(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    raw_rating = request.POST.get("rating", "").strip()

    try:
        rating_value = int(raw_rating)
    except (TypeError, ValueError):
        rating_value = None

    if rating_value is not None and 1 <= rating_value <= 10:
        Rating.objects.update_or_create(
            user=request.user,
            post=post,
            defaults={"value": rating_value},
        )

    current_user_rating = (
        Rating.objects.filter(user=request.user, post=post)
        .values_list("value", flat=True)
        .first()
    )
    rating_agg = post.ratings.aggregate(avg_rating=Avg("value"), ratings_count=Count("id"))

    if _wants_json(request):
        return JsonResponse({
            "post_id": post.id,
            "current_user_rating": current_user_rating,
            "avg_rating": rating_agg["avg_rating"],
            "ratings_count": rating_agg["ratings_count"] or 0,
        })

    next_url = request.POST.get("next", "feed")
    return redirect(next_url)


@login_required
@require_POST
def post_comment(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    text = request.POST.get("text", "").strip()
    parent_id = request.POST.get("parent_id", "").strip()

    parent_comment = None
    if parent_id:
        try:
            parsed_parent_id = int(parent_id)
        except (TypeError, ValueError):
            parsed_parent_id = None

        if parsed_parent_id is not None:
            parent_comment = Comment.objects.filter(
                pk=parsed_parent_id,
                post=post,
            ).first()

    created = False
    created_comment = None
    if text:
        created_comment = Comment.objects.create(
            user=request.user,
            post=post,
            text=text,
            parent=parent_comment,
        )
        created = True

    if _wants_json(request):
        payload = {
            "post_id": post.id,
            "created": created,
            "comments_count": post.comments.count(),
        }

        if created_comment is not None:
            profile = getattr(request.user, "profile", None)
            avatar_url = profile.avatar.url if profile and profile.avatar else ""
            payload["comment"] = {
                "id": created_comment.id,
                "parent_id": created_comment.parent_id,
                "text": created_comment.text,
                "username": request.user.username,
                "avatar_url": avatar_url,
                "username_initial": request.user.username[:1].upper(),
                "created_at": timezone.localtime(created_comment.created_at).strftime("%b %d, %Y %H:%M"),
            }

        return JsonResponse(payload)

    next_url = request.POST.get("next", "feed")
    return redirect(next_url)


@login_required
@require_POST
def comment_like(request, comment_id):
    comment = get_object_or_404(Comment, pk=comment_id)
    existing_likes = CommentLike.objects.filter(user=request.user, comment=comment)
    liked = True
    if existing_likes.exists():
        existing_likes.delete()
        liked = False
    else:
        CommentLike.objects.create(user=request.user, comment=comment)

    if _wants_json(request):
        return JsonResponse({
            "comment_id": comment.id,
            "liked": liked,
            "likes_count": comment.likes.count(),
        })

    next_url = request.POST.get("next", "feed")
    return redirect(next_url)


def profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    # Ensure profile exists (for users created before the Profile model)
    Profile.objects.get_or_create(user=profile_user)
    user_posts = (
        Post.objects.filter(user=profile_user)
        .select_related("user", "user__profile")
        .prefetch_related("images", COMMENT_PREFETCH)
        .annotate(
            avg_rating=Avg("ratings__value"),
            ratings_count=Count("ratings", distinct=True),
            comments_count=Count("comments", distinct=True),
        )
    )
    liked_posts = (
        Post.objects.filter(likes__user=profile_user)
        .select_related("user", "user__profile")
        .prefetch_related("images", COMMENT_PREFETCH)
        .annotate(
            avg_rating=Avg("ratings__value"),
            ratings_count=Count("ratings", distinct=True),
            comments_count=Count("comments", distinct=True),
        )
        .order_by("-likes__created_at")
    )
    is_following = False
    if request.user.is_authenticated and request.user != profile_user:
        is_following = Follow.objects.filter(
            follower=request.user, following=profile_user
        ).exists()

    # Build set of post IDs the current user has liked (for heart button state)
    liked_ids = set()
    if request.user.is_authenticated:
        all_post_ids = set(user_posts.values_list("id", flat=True)) | set(
            liked_posts.values_list("id", flat=True)
        )
        liked_ids = set(
            Like.objects.filter(user=request.user, post_id__in=all_post_ids)
            .values_list("post_id", flat=True)
        )

    _attach_current_user_ratings(user_posts, request.user)
    _attach_current_user_ratings(liked_posts, request.user)
    _attach_current_user_comment_likes(user_posts, request.user)
    _attach_current_user_comment_likes(liked_posts, request.user)
    _attach_comment_threads(user_posts)
    _attach_comment_threads(liked_posts)

    return render(request, "posts/profile.html", {
        "profile_user": profile_user,
        "user_posts": user_posts,
        "liked_posts": liked_posts,
        "is_following": is_following,
        "followers_count": profile_user.followers.count(),
        "following_count": profile_user.following.count(),
        "liked_ids": liked_ids,
    })


@login_required
def edit_profile(request):
    # Ensure profile exists
    profile_obj, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == "POST":
        form = ProfileForm(request.POST, request.FILES, instance=profile_obj)
        if form.is_valid():
            form.save()
            return redirect("profile", username=request.user.username)
    else:
        form = ProfileForm(instance=profile_obj)
    return render(request, "posts/edit_profile.html", {"form": form})


@login_required
def toggle_follow(request, username):
    target = get_object_or_404(User, username=username)
    if target == request.user:
        return redirect("profile", username=username)
    follow, created = Follow.objects.get_or_create(
        follower=request.user, following=target
    )
    if not created:
        follow.delete()
    return redirect("profile", username=username)