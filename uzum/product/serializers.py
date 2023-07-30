from rest_framework import serializers

from uzum.sku.models import SkuAnalytics
from uzum.sku.serializers import ExtendedSkuSerializer

from .models import Product, ProductAnalytics


class CurrentProductSerializer(serializers.ModelSerializer):
    skus = serializers.SerializerMethodField()
    analytics = serializers.SerializerMethodField()
    sku_analytics = serializers.SerializerMethodField()
    shop_title = serializers.CharField(source="shop.title", read_only=True)
    shop_link = serializers.CharField(source="shop.link", read_only=True)
    category_title = serializers.CharField(source="category.title", read_only=True)
    category_title_ru = serializers.CharField(source="category.title_ru", read_only=True)
    category_id = serializers.IntegerField(source="category.categoryId", read_only=True)

    class Meta:
        model = Product
        fields = [
            "product_id",
            "title",
            "title_ru",
            "description",
            "adult",
            "characteristics",
            "photos",
            "created_at",
            "updated_at",
            "skus",
            "analytics",
            "sku_analytics",
            "shop_title",
            "shop_link",
            "category_title",
            "category_title_ru",
            "category_id",
        ]

    def get_skus(self, obj):
        return obj.skus.values("sku", "characteristics")

    def get_analytics(self, obj):
        return obj.analytics.values(
            "badges",
            "date_pretty",
            "rating",
            "reviews_amount",
            "orders_amount",
            "position_in_category",
            "position_in_shop",
            "position",
            "available_amount",
            "orders_money",
        )[:1]

    def get_sku_analytics(self, obj):
        date_pretty = obj.analytics.order_by("-created_at").first().date_pretty

        return SkuAnalytics.objects.filter(sku__product=obj, date_pretty=date_pretty).values(
            "sku",
            "full_price",
            "purchase_price",
            "available_amount",
            "date_pretty",
        )


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ("product_id", "created_at", "updated_at")

    def create(self, validated_data):
        return Product.objects.create(**validated_data)


class ExtendedProductSerializer(serializers.ModelSerializer):
    orders_amount = serializers.IntegerField(read_only=True)
    reviews_amount = serializers.IntegerField(read_only=True)
    rating = serializers.FloatField(read_only=True)
    min_price = serializers.FloatField(read_only=True, default=-1)
    max_price = serializers.FloatField(read_only=True, default=-1)
    available_amount = serializers.IntegerField(read_only=True)
    min_price = serializers.FloatField(read_only=True)
    max_price = serializers.FloatField(read_only=True)
    skus_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ("product_id", "created_at", "updated_at")


class ProductAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAnalytics
        fields = [
            "id",
            "created_at",
            "date_pretty",
            "orders_amount",
            "orders_money",
            "reviews_amount",
            "rating",
            "available_amount",
            "position_in_category",
            "position_in_shop",
            "position",
            "average_purchase_price",
        ]
        read_only_fields = ("id", "created_at", "date_pretty")

    def create(self, validated_data):
        return ProductAnalytics.objects.create(**validated_data)


class ExtendedProductAnalyticsSerializer(serializers.ModelSerializer):
    skus = ExtendedSkuSerializer(many=True, read_only=True)
    recent_analytics = ProductAnalyticsSerializer(many=True, read_only=True)
    skus_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Product
        fields = [
            "product_id",
            "created_at",
            "title",
            "title_ru",
            "description",
            "adult",
            "bonus_product",
            "is_eco",
            "is_perishable",
            "volume_discount",
            "skus_count",
            "skus",
            "recent_analytics",
        ]
