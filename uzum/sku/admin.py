from django.contrib import admin

from uzum.sku.models import Sku, SkuAnalytics


@admin.register(Sku)
class SkuAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "product",
        "updated_at",
        "discount_badge",
        "vat_price",
    )
    list_filter = (
        "charity_profit",
        "discount_badge",
        "payment_per_month",
        "video_url",
        "vat_amount",
        "vat_price",
        "vat_rate",
        "created_at",
        "updated_at",
    )


@admin.register(SkuAnalytics)
class SkuAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "created_at",
        "available_amount",
        "purchase_price",
        "full_price",
    )
    list_filter = (
        "sku",
        "created_at",
        "available_amount",
        "purchase_price",
        "full_price",
    )
