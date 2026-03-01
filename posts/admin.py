from django.contrib import admin
from .models import Post


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "user", "created_at", "lat", "lng")
    list_filter = ("created_at", "user")
    search_fields = ("title", "description", "address_text", "user__username")
    ordering = ("-created_at",)