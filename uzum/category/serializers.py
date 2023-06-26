from rest_framework.serializers import ModelSerializer
from rest_framework import serializers
from uzum.product.models import Product, ProductAnalytics, get_today_pretty
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
        fields = "__all__"
        depth = 1


class CategoryProductAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAnalytics
        fields = ["orders_amount", "reviews_amount", "available_amount"]


class CategoryProductsSerializer(ModelSerializer):
    title = serializers.CharField(source="product.title")
    shop_title = serializers.CharField(source="product.shop.title")

    class Meta:
        model = ProductAnalytics
        fields = [
            "orders_amount",
            "reviews_amount",
            "available_amount",
            "title",
            "shop_title",
        ]

    # def get_todays_analytics(self, obj):
    #     analytics = getattr(obj, "todays_analytics", [])
    #     return CategoryProductAnalyticsSerializer(analytics, many=True).data

    # def get_skus_todays_analytics(self, obj):
    #     skus = getattr(obj, "skus_todays_analytics", [])
    #     # print(len(skus))
    #     print(skus)
    #     return CategorySkuAnalyticsSerializer(skus, many=True).data


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
