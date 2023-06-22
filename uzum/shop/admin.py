from django.contrib import admin

from .models import Shop, ShopAnalytics


@admin.register(Shop)
class ShopAdmin(admin.ModelAdmin):
    list_display = ("seller_id", "title", "link", "official", "registration_date")
    list_filter = (
        "link",
        "official",
        "registration_date",
        "title",
        "created_at",
        "updated_at",
        "avatar",
        "banner",
    )
    search_fields = ("title",)


@admin.register(ShopAnalytics)
class ShopAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "shop",
        "total_products",
        "total_orders",
        "total_reviews",
        "rating",
    )
    list_filter = (
        "shop",
        "total_products",
        "total_orders",
        "total_reviews",
        "rating",
        "created_at",
    )

    search_fields = ("shop__title",)
