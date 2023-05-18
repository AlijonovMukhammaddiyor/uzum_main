from django.contrib import admin
from .models import Reply, Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = (
        "reviewId",
        "product",
        "customer",
        "amount_dislikes",
        "amount_likes",
        "is_anonymous",
    )
    list_filter = ("product", "customer", "amount_dislikes", "amount_likes")

    search_fields = ("product", "customer", "amount_dislikes", "amount_likes")

    ordering = ("reviewId", "product", "customer", "amount_dislikes", "amount_likes")


@admin.register(Reply)
class ReplyAdmin(admin.ModelAdmin):
    list_display = ("published_at", "created_at", "content", "edited", "id", "shop")
    list_filter = ("published_at", "created_at", "content", "edited", "id", "shop")

    search_fields = ("published_at", "created_at", "content", "edited", "id", "shop")

    ordering = ("published_at", "created_at", "content", "edited", "id", "shop")
