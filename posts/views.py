from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from .models import Follow, Like, Post, PostImage
from .forms import PostForm

User = get_user_model()


def feed(request):
    posts = Post.objects.select_related("user").prefetch_related("images").all()[:50]

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
def post_like(request, post_id):
    post = get_object_or_404(Post, pk=post_id)
    like, created = Like.objects.get_or_create(user=request.user, post=post)
    if not created:
        like.delete()  # unlike
    next_url = request.POST.get("next", "feed")
    return redirect(next_url)


def profile(request, username):
    profile_user = get_object_or_404(User, username=username)
    user_posts = Post.objects.filter(user=profile_user).select_related("user").prefetch_related("images")
    liked_posts = (
        Post.objects.filter(likes__user=profile_user)
        .select_related("user")
        .prefetch_related("images")
        .order_by("-likes__created_at")
    )
    is_following = False
    if request.user.is_authenticated and request.user != profile_user:
        is_following = Follow.objects.filter(
            follower=request.user, following=profile_user
        ).exists()
    return render(request, "posts/profile.html", {
        "profile_user": profile_user,
        "user_posts": user_posts,
        "liked_posts": liked_posts,
        "is_following": is_following,
        "followers_count": profile_user.followers.count(),
        "following_count": profile_user.following.count(),
    })


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