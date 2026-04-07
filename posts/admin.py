from django.contrib import admin
from .models import Post, PostReport, Tag


@admin.register(Post)
class PostAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "user",
        "created_at",
        "lat",
        "lng",
        "tag_list",
        "reports_count",
    )
    list_filter = ("created_at", "user")
    search_fields = ("title", "description", "address_text", "user__username")
    ordering = ("-created_at",)

    def tag_list(self, obj):
        return ", ".join(obj.tags.order_by("name").values_list("name", flat=True))

    tag_list.short_description = "Tags"

    def reports_count(self, obj):
        return obj.reports.count()

    reports_count.short_description = "Reports"


@admin.register(Tag)
class TagAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "created_at")
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(PostReport)
class PostReportAdmin(admin.ModelAdmin):
    list_display = ("id", "post", "reporter", "created_at", "reason")
    list_filter = ("created_at",)
    search_fields = (
        "post__title",
        "post__user__username",
        "reporter__username",
        "reason",
    )
    ordering = ("-created_at",)