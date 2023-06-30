from rest_framework.serializers import ModelSerializer
from rest_framework import serializers
from uzum.badge.serializers import ProductBadgeSerializer
from uzum.product.models import Product, ProductAnalytics, ProductAnalyticsView, get_today_pretty
from uzum.sku.models import Sku, SkuAnalytics
from django.db.models import Prefetch
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
        fields = "__all__"
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


class CategoryProductBadgeSerializer(serializers.Serializer):
    badge_text_list = serializers.ListField(child=serializers.CharField(), source="badge_text")
    badge_background_color_list = serializers.ListField(child=serializers.CharField(), source="badge_background_color")
    badge_text_color_list = serializers.ListField(child=serializers.CharField(), source="badge_text_color")


class CategoryProductsViewSerializer(serializers.ModelSerializer):
    purchase_price_list = serializers.ListField(child=serializers.FloatField())
    full_price_list = serializers.ListField(child=serializers.FloatField())
    badge_text_list = serializers.ListField(child=serializers.CharField())
    badge_background_color_list = serializers.ListField(child=serializers.CharField())
    badge_text_color_list = serializers.ListField(child=serializers.CharField())

    class Meta:
        model = ProductAnalyticsView
        fields = [
            "product_id",
            "product_title",
            "orders_amount",
            "available_amount",
            "reviews_amount",
            "shop_title",
            "shop_link",
            "badge_text_list",
            "badge_background_color_list",
            "badge_text_color_list",
            "purchase_price_list",
            "full_price_list",
            "category_id",
            "photos",
        ]


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
