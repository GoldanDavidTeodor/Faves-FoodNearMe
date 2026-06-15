import random
import math
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_GET
from django.views.decorators.http import require_POST
from django.db.models import Avg, Count, Prefetch, Q, Value, FloatField, ExpressionWrapper, F
from django.db.models.functions import ACos, Cos, Sin, Radians, Greatest, Least
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from datetime import timedelta
from .models import Comment, CommentLike, Follow, Like, LocationPreset, Message, Post, PostImage, PostReport, Profile, Rating, Tag
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


FEED_PAGE_SIZE = 20


def _parse_positive_int(value, default=1):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed >= 1 else default


def _clean_next_url(request):
    """Return a safe `next` URL for form redirects.

    We intentionally strip pagination/partial params so form POST redirects never land
    on a partial HTML endpoint.
    """
    params = request.GET.copy()
    params.pop("partial", None)
    params.pop("page", None)
    qs = params.urlencode()
    return f"{request.path}?{qs}" if qs else request.path


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


def _parse_feed_tags_filter(request):
    raw = (request.GET.get("tags") or "").strip()
    if not raw:
        return []

    parts = [p.strip().lower() for p in raw.split(",")]
    cleaned = []
    seen = set()
    for p in parts:
        if not p:
            continue
        if p.startswith("#"):
            p = p[1:]
        if not p:
            continue
        if p not in seen:
            seen.add(p)
            cleaned.append(p)

    return cleaned


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

    selected_tags = _parse_feed_tags_filter(request)

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

    if selected_tags:
        posts_qs = (
            posts_qs.annotate(
                matched_tags_count=Count(
                    "tags",
                    filter=Q(tags__name__in=selected_tags),
                    distinct=True,
                )
            )
            .filter(matched_tags_count__gt=0)
            .order_by("-matched_tags_count", "-created_at", "-id")
        )
    else:
        posts_qs = posts_qs.order_by("-created_at", "-id")

    page = _parse_positive_int(request.GET.get("page"), default=1)
    page_size = FEED_PAGE_SIZE
    start = (page - 1) * page_size
    window = list(posts_qs[start:start + page_size + 1])
    posts = window[:page_size]
    has_more = len(window) > page_size

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

    next_url = _clean_next_url(request)
    is_partial = request.GET.get("partial") == "1"
    if is_partial:
        resp = render(request, "posts/_feed_post_cards.html", {
            "posts": posts,
            "liked_ids": liked_ids,
            "next_url": next_url,
        })
        resp["X-Has-More"] = "1" if has_more else "0"
        resp["X-Next-Page"] = str(page + 1)
        return resp

    followers = []
    if request.user.is_authenticated:
        followers = _get_followers_for_user(request.user)

    return render(request, "posts/feed.html", {
        "page_title": "Feed",
        "next_url": next_url,
        "page_mode": "feed",
        "posts": posts,
        "has_more": has_more,
        "liked_ids": liked_ids,
        "followers": followers,
        "post_locations": post_locations,
        "location_filter": {
            "active": has_location_filter,
            "lat": filter_lat,
            "lng": filter_lng,
            "range_km": filter_range_km,
        },
        "selected_tags": selected_tags,
    })


def explore(request):
    """Map-first Explore page: big map in the main column, selected post shown on the right."""
    selected_tags = _parse_feed_tags_filter(request)
    has_location_filter, filter_lat, filter_lng, filter_range_km = _parse_feed_location_filter(request)

    posts_qs = _get_feed_posts_queryset(
        has_location_filter=has_location_filter,
        filter_lat=filter_lat,
        filter_lng=filter_lng,
        filter_range_km=filter_range_km,
    )

    posts_qs = posts_qs.filter(lat__isnull=False, lng__isnull=False)

    if selected_tags:
        posts_qs = (
            posts_qs.annotate(
                matched_tags_count=Count(
                    "tags",
                    filter=Q(tags__name__in=selected_tags),
                    distinct=True,
                )
            )
            .filter(matched_tags_count__gt=0)
            .order_by("-matched_tags_count", "-created_at", "-id")
        )
    else:
        posts_qs = posts_qs.order_by("-created_at", "-id")

    posts = list(posts_qs[:220])

    liked_ids = set()
    if request.user.is_authenticated and posts:
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
        "page_title": "Explore",
        "next_url": request.get_full_path(),
        "page_mode": "explore_map",
        "container_max": "100%",
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
        "selected_tags": selected_tags,
    })


def _haversine_km(lat1, lng1, lat2, lng2):
    """Great-circle distance (km) between two lat/lng points."""
    try:
        lat1 = float(lat1)
        lng1 = float(lng1)
        lat2 = float(lat2)
        lng2 = float(lng2)
    except (TypeError, ValueError):
        return None

    r = 6371.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lng2 - lng1)

    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return r * c


def _build_for_you_user_signals(user):
    """Return (tag_affinity, own_tags_set, following_ids, reference_location)."""
    now = timezone.now()

    following_ids = set(
        Follow.objects.filter(follower=user).values_list("following_id", flat=True)
    )

    tag_affinity = {}
    rated = (
        Rating.objects.filter(user=user)
        .select_related("post")
        .prefetch_related("post__tags")
        .order_by("-updated_at")[:500]
    )

    for rating in rated:
        age_days = max(0.0, (now - rating.updated_at).total_seconds() / 86400.0)
        recency = 0.985 ** age_days
        centered = (float(rating.value) - 5.5) / 4.5
        for tag in rating.post.tags.all():
            tag_affinity[tag.name] = tag_affinity.get(tag.name, 0.0) + centered * recency

    own_tags_set = set()
    own_posts = (
        Post.objects.filter(user=user)
        .prefetch_related("tags")
        .order_by("-created_at")[:120]
    )
    for post in own_posts:
        age_days = max(0.0, (now - post.created_at).total_seconds() / 86400.0)
        recency = 0.99 ** age_days
        for tag in post.tags.all():
            own_tags_set.add(tag.name)
            tag_affinity[tag.name] = tag_affinity.get(tag.name, 0.0) + 0.35 * recency

    reference_lat = None
    reference_lng = None
    latest_preset = (
        LocationPreset.objects.filter(user=user)
        .order_by("-created_at", "-id")
        .values("lat", "lng")
        .first()
    )
    if latest_preset:
        try:
            reference_lat = float(latest_preset["lat"])
            reference_lng = float(latest_preset["lng"])
        except (TypeError, ValueError):
            reference_lat = None
            reference_lng = None

    return tag_affinity, own_tags_set, following_ids, (reference_lat, reference_lng)


def _score_for_you_post(
    *,
    post,
    tag_affinity,
    own_tags_set,
    following_ids,
    reference_location,
    user_rating_value=None,
):
    """Compute a weighted score for a post for For You ranking."""
    W_TAG = 4.0
    W_FOLLOW = 1.8
    W_DISTANCE = 2.2
    W_OWN_OVERLAP = 1.2
    W_QUALITY = 0.7
    W_FRESH = 0.35
    W_USER_RATING = 12.0

    tags = [t.name for t in post.tags.all()]

    tag_component = 0.0
    if tags:
        for name in tags:
            tag_component += float(tag_affinity.get(name, 0.0))
        tag_component = tag_component / math.sqrt(len(tags))

    follow_component = 1.0 if post.user_id in following_ids else 0.0

    own_overlap_component = 0.0
    if own_tags_set and tags:
        tag_set = set(tags)
        if tag_set:
            own_overlap_component = len(tag_set & own_tags_set) / len(tag_set)

    distance_component = 0.0
    ref_lat, ref_lng = reference_location
    if ref_lat is not None and ref_lng is not None and post.lat is not None and post.lng is not None:
        dist_km = _haversine_km(ref_lat, ref_lng, post.lat, post.lng)
        if dist_km is not None:
            distance_component = max(0.0, 1.0 - (dist_km / 25.0))

    quality_component = 0.0
    if getattr(post, "avg_rating", None) is not None:
        avg = float(post.avg_rating)
        avg_norm = max(0.0, min(1.0, (avg - 1.0) / 9.0))
        cnt = float(getattr(post, "ratings_count", 0) or 0)
        confidence = max(0.0, min(1.0, math.log1p(cnt) / math.log1p(20.0)))
        quality_component = avg_norm * confidence

    fresh_component = 0.0
    if getattr(post, "created_at", None) is not None:
        age_days = max(0.0, (timezone.now() - post.created_at).total_seconds() / 86400.0)
        fresh_component = math.exp(-age_days / 14.0)

    user_rating_component = 0.0
    if user_rating_value is not None:
        try:
            user_rating_value = int(user_rating_value)
        except (TypeError, ValueError):
            user_rating_value = None

    if user_rating_value is not None:
        if user_rating_value <= 3:
            return -1_000_000.0
        centered = (float(user_rating_value) - 5.5) / 4.5
        user_rating_component = centered

    score = (
        W_TAG * tag_component
        + W_FOLLOW * follow_component
        + W_DISTANCE * distance_component
        + W_OWN_OVERLAP * own_overlap_component
        + W_QUALITY * quality_component
        + W_FRESH * fresh_component
        + W_USER_RATING * user_rating_component
    )
    return score


@require_GET
def tag_suggest(request):
    q = (request.GET.get("q") or "").strip().lower()
    if q.startswith("#"):
        q = q[1:]

    tags_qs = Tag.objects.all().annotate(posts_count=Count("posts", distinct=True))
    if q:
        tags_qs = tags_qs.filter(name__icontains=q)

    tags = list(tags_qs.order_by("-posts_count", "name").values_list("name", flat=True)[:12])
    return JsonResponse({"tags": tags})


@require_GET
def tag_popular(request):
    """Return all-time most-used tags (by number of distinct posts)."""
    tags = list(
        Tag.objects.all()
        .annotate(posts_count=Count("posts", distinct=True))
        .order_by("-posts_count", "name")
        .values_list("name", flat=True)[:12]
    )
    return JsonResponse({"tags": tags})


@require_GET
def tag_hot(request):
    """Return tags used most on posts within the last N days."""
    raw_days = (request.GET.get("days") or "").strip()
    try:
        days = int(raw_days) if raw_days else 14
    except ValueError:
        days = 14

    days = max(1, min(90, days))
    since = timezone.now() - timedelta(days=days)

    tags_qs = (
        Tag.objects.filter(posts__created_at__gte=since)
        .annotate(posts_count=Count("posts", filter=Q(posts__created_at__gte=since), distinct=True))
        .filter(posts_count__gt=0)
        .order_by("-posts_count", "name")
    )

    tags = list(tags_qs.values_list("name", flat=True)[:12])
    return JsonResponse({"tags": tags, "days": days})


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


@login_required
def for_you(request):
    selected_tags = _parse_feed_tags_filter(request)

    has_location_filter, filter_lat, filter_lng, filter_range_km = _parse_feed_location_filter(request)
    posts_qs = _get_feed_posts_queryset(
        has_location_filter=has_location_filter,
        filter_lat=filter_lat,
        filter_lng=filter_lng,
        filter_range_km=filter_range_km,
    )

    if selected_tags:
        posts_qs = (
            posts_qs.annotate(
                matched_tags_count=Count(
                    "tags",
                    filter=Q(tags__name__in=selected_tags),
                    distinct=True,
                )
            )
            .filter(matched_tags_count__gt=0)
        )

    if request.user.is_authenticated:
        posts_qs = posts_qs.exclude(reports__reporter=request.user)

    candidates = list(posts_qs.order_by("-created_at", "-id")[:450])

    if request.user.is_authenticated and candidates:
        tag_affinity, own_tags_set, following_ids, preset_reference = _build_for_you_user_signals(request.user)
        reference_location = (
            (filter_lat, filter_lng) if has_location_filter else preset_reference
        )

        user_ratings_by_post_id = dict(
            Rating.objects.filter(
                user=request.user,
                post_id__in=[p.id for p in candidates],
            ).values_list("post_id", "value")
        )

        scored = []
        for post in candidates:
            s = _score_for_you_post(
                post=post,
                tag_affinity=tag_affinity,
                own_tags_set=own_tags_set,
                following_ids=following_ids,
                reference_location=reference_location,
                user_rating_value=user_ratings_by_post_id.get(post.id),
            )
            scored.append((s, post.created_at, post.id, post))

        scored.sort(key=lambda row: (row[0], row[1], row[2]), reverse=True)
        ordered = [row[3] for row in scored]
    else:
        ordered = candidates

    page = _parse_positive_int(request.GET.get("page"), default=1)
    page_size = FEED_PAGE_SIZE
    start = (page - 1) * page_size
    window = ordered[start:start + page_size + 1]
    posts = window[:page_size]
    has_more = len(window) > page_size

    liked_ids = set()
    if request.user.is_authenticated and posts:
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

    next_url = _clean_next_url(request)
    is_partial = request.GET.get("partial") == "1"
    if is_partial:
        resp = render(request, "posts/_feed_post_cards.html", {
            "posts": posts,
            "liked_ids": liked_ids,
            "next_url": next_url,
        })
        resp["X-Has-More"] = "1" if has_more else "0"
        resp["X-Next-Page"] = str(page + 1)
        return resp

    followers = []
    if request.user.is_authenticated:
        followers = _get_followers_for_user(request.user)

    return render(request, "posts/feed.html", {
        "page_title": "For You",
        "next_url": next_url,
        "page_mode": "for_you",
        "posts": posts,
        "has_more": has_more,
        "liked_ids": liked_ids,
        "followers": followers,
        "post_locations": post_locations,
        "location_filter": {
            "active": has_location_filter,
            "lat": filter_lat,
            "lng": filter_lng,
            "range_km": filter_range_km,
        },
        "selected_tags": selected_tags,
    })


@login_required
def location_presets(request):
    if request.method == "GET":
        presets = (
            LocationPreset.objects
            .filter(user=request.user)
            .order_by("name", "id")
            .values("id", "name", "lat", "lng")
        )

        items = []
        for p in presets:
            try:
                lat = float(p["lat"])
                lng = float(p["lng"])
            except (TypeError, ValueError):
                continue
            items.append({
                "id": p["id"],
                "name": p["name"],
                "lat": lat,
                "lng": lng,
            })

        return JsonResponse({"presets": items})

    if request.method == "POST":
        if not _wants_json(request):
            return JsonResponse({"error": "Expected AJAX request"}, status=400)

        try:
            import json

            payload = json.loads(request.body or "{}")
        except Exception:
            payload = {}

        name = (payload.get("name") or "").strip()
        lat = payload.get("lat")
        lng = payload.get("lng")

        if not name:
            return JsonResponse({"error": "Name is required"}, status=400)

        if len(name) > 60:
            return JsonResponse({"error": "Name must be 60 characters or fewer"}, status=400)

        try:
            lat = float(lat)
            lng = float(lng)
        except (TypeError, ValueError):
            return JsonResponse({"error": "Invalid coordinates"}, status=400)

        if not (-90.0 <= lat <= 90.0 and -180.0 <= lng <= 180.0):
            return JsonResponse({"error": "Coordinates out of range"}, status=400)

        preset, created = LocationPreset.objects.get_or_create(
            user=request.user,
            name=name,
            defaults={"lat": lat, "lng": lng},
        )

        if not created:
            preset.lat = lat
            preset.lng = lng
            preset.save(update_fields=["lat", "lng"])

        return JsonResponse({
            "created": created,
            "preset": {
                "id": preset.id,
                "name": preset.name,
                "lat": float(preset.lat),
                "lng": float(preset.lng),
            },
        })

    return JsonResponse({"error": "Method not allowed"}, status=405)


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
                .prefetch_related("images", "tags", COMMENT_PREFETCH)
                .annotate(
                    avg_rating=Avg("ratings__value"),
                    ratings_count=Count("ratings", distinct=True),
                    comments_count=Count("comments", distinct=True),
                )
            )

            for post in shared_posts:
                Profile.objects.get_or_create(user=post.user)

            _attach_current_user_ratings(shared_posts, request.user)
            _attach_current_user_comment_likes(shared_posts, request.user)
            _attach_comment_threads(shared_posts)

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
        "next_url": request.get_full_path(),
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