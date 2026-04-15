import random
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.db.models import Avg, Count, Prefetch, Q, Value, FloatField, ExpressionWrapper, F
from django.db.models.functions import ACos, Cos, Sin, Radians, Greatest, Least
from django.http import JsonResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from datetime import timedelta
from .models import Comment, CommentLike, Follow, Like, Message, Post, PostImage, PostReport, Profile, Rating
from .forms import MessageForm, PostForm, ProfileForm

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


def _get_followers_for_user(user):
    followers_qs = (
        Follow.objects.filter(following=user)
        .select_related("follower")
        .order_by("-created_at")
    )

    follower_users = []
    for follow in followers_qs:
        follower = follow.follower
        Profile.objects.get_or_create(user=follower)
        follower_users.append(follower)

    return follower_users


def _parse_feed_location_filter(request):
    def _parse_float(raw_value):
        try:
            return float(raw_value)
        except (TypeError, ValueError):
            return None

    filter_lat = _parse_float(request.GET.get("lat"))
    filter_lng = _parse_float(request.GET.get("lng"))
    filter_range_km = _parse_float(request.GET.get("range_km"))

    has_location_filter = (
        filter_lat is not None
        and filter_lng is not None
        and filter_range_km is not None
        and -90.0 <= filter_lat <= 90.0
        and -180.0 <= filter_lng <= 180.0
        and 0.0 < filter_range_km <= 250.0
    )

    return has_location_filter, filter_lat, filter_lng, filter_range_km


def _get_feed_posts_queryset(*, has_location_filter, filter_lat, filter_lng, filter_range_km):
    posts_qs = (
        Post.objects.select_related("user", "user__profile")
        .prefetch_related("images", "tags", COMMENT_PREFETCH)
        .annotate(
            avg_rating=Avg("ratings__value"),
            ratings_count=Count("ratings", distinct=True),
            comments_count=Count("comments", distinct=True),
            shares_count=Count("shared_messages", distinct=True),
        )
    )

    if has_location_filter:
        # Spherical law of cosines distance (km), clamped to avoid ACos domain errors.
        lat0 = Radians(Value(filter_lat))
        lng0 = Radians(Value(filter_lng))
        lat1 = Radians(F("lat"))
        lng1 = Radians(F("lng"))

        cosine_angle = (
            Cos(lat0) * Cos(lat1) * Cos(lng1 - lng0)
            + Sin(lat0) * Sin(lat1)
        )
        cosine_angle = Least(Value(1.0), Greatest(Value(-1.0), cosine_angle))

        distance_km = ExpressionWrapper(
            Value(6371.0) * ACos(cosine_angle),
            output_field=FloatField(),
        )

        posts_qs = (
            posts_qs.filter(lat__isnull=False, lng__isnull=False)
            .annotate(distance_km=distance_km)
            .filter(distance_km__lte=filter_range_km)
        )

    return posts_qs


def feed(request):
    raw_query = request.GET.get("q")
    search_query = (raw_query or "").strip()

    has_location_filter, filter_lat, filter_lng, filter_range_km = _parse_feed_location_filter(request)
    posts_qs = _get_feed_posts_queryset(
        has_location_filter=has_location_filter,
        filter_lat=filter_lat,
        filter_lng=filter_lng,
        filter_range_km=filter_range_km,
    )

    if search_query:
        posts_qs = posts_qs.filter(
            Q(title__icontains=search_query) | Q(description__icontains=search_query)
        )

    posts = posts_qs.order_by("-created_at", "-id")[:50]

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

    post_locations = []
    for post in posts:
        if post.lat is None or post.lng is None:
            continue
        try:
            lat = float(post.lat)
            lng = float(post.lng)
        except (TypeError, ValueError):
            continue

        post_locations.append({
            "id": post.id,
            "title": post.title,
            "username": post.user.username,
            "lat": lat,
            "lng": lng,
        })

    followers = []
    if request.user.is_authenticated:
        followers = _get_followers_for_user(request.user)

    return render(request, "posts/feed.html", {
        "posts": posts,
        "liked_ids": liked_ids,
        "followers": followers,
        "post_locations": post_locations,
        "location_filter": {
            "active": has_location_filter,
            "lat": filter_lat,
            "lng": filter_lng,
            "range_km": filter_range_km,
        },
    })


def surprise_me(request):
    """Redirect to the feed anchored on a random post card."""
    has_location_filter, filter_lat, filter_lng, filter_range_km = _parse_feed_location_filter(request)
    posts_qs = _get_feed_posts_queryset(
        has_location_filter=has_location_filter,
        filter_lat=filter_lat,
        filter_lng=filter_lng,
        filter_range_km=filter_range_km,
    )

    post_ids = list(
        posts_qs.order_by("-created_at", "-id")
        .values_list("id", flat=True)[:50]
    )

    if not post_ids:
        return redirect("feed")

    post_id = random.choice(post_ids)
    base_url = reverse("feed")
    params = request.GET.copy()
    params["open_post"] = str(post_id)
    query = params.urlencode()
    if query:
        base_url = f"{base_url}?{query}"

    return redirect(f"{base_url}#post-{post_id}")


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
            form.apply_tags(post)
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
        .prefetch_related("images", "tags", COMMENT_PREFETCH)
        .annotate(
            avg_rating=Avg("ratings__value"),
            ratings_count=Count("ratings", distinct=True),
            comments_count=Count("comments", distinct=True),
            forwards_count=Count("shared_messages", distinct=True),
        )
    )
    liked_posts = (
        Post.objects.filter(likes__user=profile_user)
        .select_related("user", "user__profile")
        .prefetch_related("images", "tags", COMMENT_PREFETCH)
        .annotate(
            avg_rating=Avg("ratings__value"),
            ratings_count=Count("ratings", distinct=True),
            comments_count=Count("comments", distinct=True),
            forwards_count=Count("shared_messages", distinct=True),
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

    received_likes_count = Like.objects.filter(post__user=profile_user).count()

    return render(request, "posts/profile.html", {
        "profile_user": profile_user,
        "user_posts": user_posts,
        "liked_posts": liked_posts,
        "is_following": is_following,
        "followers_count": profile_user.followers.count(),
        "following_count": profile_user.following.count(),
        "received_likes_count": received_likes_count,
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


@login_required
def messages(request, username=None):
    follower_users = _get_followers_for_user(request.user)

    selected_user = None
    thread_messages = []
    thread_items = []
    form = MessageForm()

    if username:
        selected_user = get_object_or_404(User, username=username)
        is_follower = Follow.objects.filter(
            follower=selected_user,
            following=request.user,
        ).exists()
        if not is_follower:
            return render(request, "posts/messages.html", {
                "followers": follower_users,
                "selected_user": None,
                "thread_messages": [],
                "form": form,
                "error": "You can only message people who follow you.",
            }, status=404)

        if request.method == "POST":
            form = MessageForm(request.POST)
            if form.is_valid():
                text = form.cleaned_data["text"].strip()
                if text:
                    Message.objects.create(
                        sender=request.user,
                        recipient=selected_user,
                        text=text,
                    )
                return redirect("messages_thread", username=selected_user.username)

        thread_messages = list(
            Message.objects.filter(
                Q(sender=request.user, recipient=selected_user)
                | Q(sender=selected_user, recipient=request.user)
            )
            .select_related("sender", "recipient", "post")
            .order_by("created_at")
        )

        shared_post_ids = [m.post_id for m in thread_messages if m.post_id]
        shared_posts = []
        liked_ids = set()

        if shared_post_ids:
            shared_posts = list(
                Post.objects.filter(id__in=shared_post_ids)
                .select_related("user", "user__profile")
                .prefetch_related("images", "tags")
                .annotate(
                    avg_rating=Avg("ratings__value"),
                    ratings_count=Count("ratings", distinct=True),
                    comments_count=Count("comments", distinct=True),
                )
            )

            for post in shared_posts:
                Profile.objects.get_or_create(user=post.user)

            _attach_current_user_ratings(shared_posts, request.user)

            liked_ids = set(
                Like.objects.filter(user=request.user, post_id__in=shared_post_ids)
                .values_list("post_id", flat=True)
            )

            posts_by_id = {p.id: p for p in shared_posts}
            for msg in thread_messages:
                if msg.post_id and msg.post_id in posts_by_id:
                    msg.post = posts_by_id[msg.post_id]

        # Insert date separators only when there is a longer pause between messages
        gap_threshold = timedelta(hours=6)
        previous_dt = None
        previous_date = None
        for msg in thread_messages:
            current_dt = timezone.localtime(msg.created_at)
            current_date = current_dt.date()
            if previous_dt is None:
                thread_items.append({
                    "kind": "separator",
                    "label": current_dt.strftime("%b %d, %Y"),
                })
            else:
                if current_date != previous_date or (current_dt - previous_dt) >= gap_threshold:
                    thread_items.append({
                        "kind": "separator",
                        "label": current_dt.strftime("%b %d, %Y"),
                    })

            thread_items.append({
                "kind": "message",
                "message": msg,
            })
            previous_dt = current_dt
            previous_date = current_date

        # Mark incoming messages as read when viewing the thread
        Message.objects.filter(
            sender=selected_user,
            recipient=request.user,
            read_at__isnull=True,
        ).update(read_at=timezone.now())

    return render(request, "posts/messages.html", {
        "followers": follower_users,
        "selected_user": selected_user,
        "thread_messages": thread_messages,
        "thread_items": thread_items,
        "liked_ids": liked_ids if username else set(),
        "form": form,
    })


@login_required
@require_POST
def post_share(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    recipient_username = request.POST.get("recipient", "").strip()
    recipient = get_object_or_404(User, username=recipient_username)

    if recipient == request.user:
        if _wants_json(request):
            return JsonResponse({"ok": False}, status=400)
        return redirect("feed")

    can_message = Follow.objects.filter(
        follower=recipient,
        following=request.user,
    ).exists()
    if not can_message:
        if _wants_json(request):
            return JsonResponse({"ok": False}, status=403)
        return redirect("feed")

    Message.objects.create(
        sender=request.user,
        recipient=recipient,
        post=post,
        text="",
    )

    if _wants_json(request):
        return JsonResponse({
            "ok": True,
            "post_id": post.id,
            "shares_count": post.shared_messages.count(),
        })

    return redirect("feed")


@login_required
@require_POST
def post_report(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    reason = request.POST.get("reason", "").strip()

    report, created = PostReport.objects.get_or_create(
        post=post,
        reporter=request.user,
        defaults={"reason": reason},
    )

    if not created and reason and not report.reason:
        report.reason = reason
        report.save(update_fields=["reason"])

    if _wants_json(request):
        return JsonResponse({
            "ok": True,
            "created": created,
            "post_id": post.id,
        })

    next_url = request.POST.get("next", "feed")
    return redirect(next_url)