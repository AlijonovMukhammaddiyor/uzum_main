from django.contrib.postgres.fields import JSONField
from django.db.models import Prefetch
from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from uzum.badge.models import Badge
from uzum.badge.serializers import ProductBadgeSerializer
from uzum.product.models import Product, ProductAnalytics, ProductAnalyticsView
from uzum.sku.models import Sku, SkuAnalytics

from .models import Category, CategoryAnalytics


class CategoryChildSerializer(ModelSerializer):
    class Meta:
        model = Category
        fields = ["categoryId", "title"]


class CategorySerializer(ModelSerializer):
    children = CategoryChildSerializer(many=True, read_only=True)

    class Meta:
        model = Category
        fields = "__all__"


class CategoryAnalyticsSeralizer(ModelSerializer):
    class Meta:
        model = CategoryAnalytics
        fields = [
            "total_products",
            "total_orders",
            "total_orders_amount",
            "total_reviews",
            "average_product_rating",
            "total_shops",
            "total_shops_with_sales",
            "total_products_with_sales",
            "average_purchase_price",
            "date_pretty",
            "daily_revenue",
            "daily_orders",
        ]
        depth = 1


class CategoryProductAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAnalytics
        fields = ["orders_amount", "reviews_amount", "available_amount"]


class CategoryProductsSkusSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkuAnalytics
        fields = ["purchase_price", "full_price", "available_amount"]


class ProductAnalyticsViewSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAnalyticsView
        fields = [
            "product_id",
            "product_title",
            "product_title_ru",
            "product_characteristics",
            "shop_title",
            "shop_link",
            "product_available_amount",
            "orders_amount",
            "orders_money",
            "reviews_amount",
            "rating",
            "position_in_category",
            "sku_analytics",
            "badges",
            "date_pretty",
            "sku_analytics",
            "photos",
            "category_id",
            "category_title",
            "category_title_ru",
            "avg_purchase_price",
            # "diff_orders_amount",
            # "diff_orders_money",
            # "diff_reviews_amount",
            # "weekly_orders_amount",
            # "weekly_orders_money",
            # "weekly_reviews_amount",
            "product_created_at",
            "revenue_3_days",
            "orders_3_days",
            "weekly_revenue",
            "weekly_orders",
            "monthly_revenue",
            "monthly_orders",
            "revenue_90_days",
            "orders_90_days",
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["product_title"] = f"{representation['product_title']} (({representation['product_id']}))"
        representation["shop_title"] = f"{representation['shop_title']} (({representation['shop_link']}))"
        representation["category_title"] = f"{representation['category_title']} (({representation['category_id']}))"

        representation[
            "product_title_ru"
        ] = f"{representation['product_title_ru'] if representation['product_title_ru'] else representation['product_title']} (({representation['product_id']}))"
        representation[
            "category_title_ru"
        ] = f"{representation['category_title_ru']} (({representation['category_id']}))"

        return representation


class CategorySkuAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkuAnalytics
        fields = ["available_amount", "purchase_price", "full_price"]


class CategorySkuSerializer(serializers.ModelSerializer):
    analytics = serializers.SerializerMethodField()

    class Meta:
        model = Sku
        fields = [
            "video_url",
            "characteristics",
            "analytics",
        ]

    def get_analytics(self, obj):
        analytics = getattr(obj, "analytics", [])
        return CategorySkuAnalyticsSerializer(analytics, many=True).data
