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


class SimpleCategorySerializer(ModelSerializer):
    class Meta:
        model = Category
        fields = ["categoryId", "title"]


class CategoryAnalyticsSeralizer(ModelSerializer):
    class Meta:
        model = CategoryAnalytics
        fields = [
            "total_products",
            "total_orders",
            "total_reviews",
            "average_product_rating",
            "total_shops",
            "total_shops_with_sales",
            "total_products_with_sales",
            "average_purchase_price",
            "date_pretty",
        ]
        depth = 1


class CategoryProductAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAnalytics
        fields = ["orders_amount", "reviews_amount", "available_amount"]


class CategoryProductsSerializer(ModelSerializer):
    title = serializers.CharField(source="product.title")
    product_id = serializers.IntegerField(source="product.product_id")
    shop_title = serializers.CharField(source="product.shop.title")
    photos = serializers.CharField(source="product.photos")
    skus = serializers.SerializerMethodField()
    sku_count = serializers.SerializerMethodField()
    badges = ProductBadgeSerializer(source="badges.all", read_only=True, many=True)  # new line

    class Meta:
        model = ProductAnalytics
        fields = [
            "orders_amount",
            "position_in_category",
            "product_id",
            "reviews_amount",
            "available_amount",
            "title",
            "shop_title",
            "skus",
            "sku_count",
            "photos",
            "badges",
        ]

    def get_skus(self, obj):
        # Serialize each SKU's latest price.
        return [
            {
                sku.sku: {
                    "purchase_price": sku.todays_analytics[0].purchase_price if sku.todays_analytics else None,
                    "full_price": sku.todays_analytics[0].full_price if sku.todays_analytics else None,
                }
                if sku.todays_analytics
                else None
            }
            for sku in obj.product.skus.all()
        ]

    def get_sku_count(self, obj):
        return obj.product.skus.count()


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
            "product_characteristics",
            "shop_title",
            "shop_link",
            "product_available_amount",
            "orders_amount",
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
            "avg_purchase_price",
        ]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["product_title"] = f"{representation['product_title']} (({representation['product_id']}))"
        representation["shop_title"] = f"{representation['shop_title']} (({representation['shop_link']}))"
        representation["category_title"] = f"{representation['category_title']} (({representation['category_id']}))"
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
