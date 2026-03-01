from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from .models import Post
from .forms import PostForm


def feed(request):
    posts = Post.objects.select_related("user").all()[:50]
    return render(request, "posts/feed.html", {"posts": posts})


@login_required
def post_create(request):
    if request.method == "POST":
        form = PostForm(request.POST)
        if form.is_valid():
            post = form.save(commit=False)
            post.user = request.user
            post.save()
            return redirect("feed")
    else:
        form = PostForm()

    return render(request, "posts/post_form.html", {"form": form})