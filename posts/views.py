from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_POST
from django.shortcuts import get_object_or_404, redirect, render
from .models import Follow, Like, Post, PostImage, Profile
from .forms import PostForm, ProfileForm

User = get_user_model()


def feed(request):
    posts = (
        Post.objects.select_related("user", "user__profile")
        .prefetch_related("images")
        .all()[:50]
    )

    # Build a set of post IDs the current user has liked
    liked_ids = set()
    if request.user.is_authenticated:
        liked_ids = set(
            Like.objects.filter(user=request.user, post__in=posts)
            .values_list("post_id", flat=True)
        )

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
    if existing_likes.exists():
        existing_likes.delete()
    else:
        Like.objects.create(user=request.user, post=post)
    next_url = request.POST.get("next", "feed")
    return redirect(next_url)


def profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    # Ensure profile exists (for users created before the Profile model)
    Profile.objects.get_or_create(user=profile_user)
    user_posts = (
        Post.objects.filter(user=profile_user)
        .select_related("user", "user__profile")
        .prefetch_related("images")
    )
    liked_posts = (
        Post.objects.filter(likes__user=profile_user)
        .select_related("user", "user__profile")
        .prefetch_related("images")
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