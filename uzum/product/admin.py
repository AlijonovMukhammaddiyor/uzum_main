from django.contrib import admin
from uzum.product.models import Product, ProductAnalytics


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = (
        "product_id",
        "title",
        "video",
        "created_at",
        "updated_at",
        "shop",
        "category",
    )
    list_filter = (
        "title",
        "description",
        "adult",
        "is_eco",
        "shop",
        "is_perishable",
        "bonus_product",
        "category",
    )


@admin.register(ProductAnalytics)
class ProductAnalyticsAdmin(admin.ModelAdmin):
    list_display = (
        "created_at",
        "product",
        "reviews_amount",
        "rating",
        "orders_amount",
        "shop",
        "category",
    )
    list_filter = (
        "product",
        "reviews_amount",
        "rating",
        "orders_amount",
        "created_at",
    )

    search_fields = ("product__title", "product__product_id", "product__shop__title")

    def shop(self, obj):
        return obj.product.shop

    def category(self, obj):
        return obj.product.category.title
