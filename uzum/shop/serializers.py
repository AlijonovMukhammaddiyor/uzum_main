from rest_framework.serializers import ModelSerializer
from .models import Shop, ShopAnalytics
from rest_framework import serializers


class ShopSerializer(ModelSerializer):
    class Meta:
        model = Shop
        fields = [
            "seller_id",
            "account_id",
            "title",
            "banner",
            "avatar",
            "description",
            "link",
            "official",
            "info",
            "registration_date",
            "created_at",
            "updated_at",
        ]


class ShopAnalyticsSerializer(ModelSerializer):
    class Meta:
        model = ShopAnalytics
        fields = [
            "id",
            "shop",
            "created_at",
            "total_products",
            "total_orders",
            "total_reviews",
            "rating",
            "date_pretty",
            "score",
            "daily_position",
        ]


class ExtendedShopSerializer(ShopSerializer):
    order_difference = serializers.IntegerField()
    total_orders = serializers.IntegerField()
    total_products = serializers.IntegerField()
    total_reviews = serializers.IntegerField()
    rating = serializers.FloatField()
    date_pretty = serializers.CharField()

    class Meta:
        model = Shop
        fields = ShopSerializer.Meta.fields + [
            "total_orders",
            "order_difference",
            "total_products",
            "total_reviews",
            "rating",
            "date_pretty",
        ]


class ShopCompetitorsSerializer(ShopAnalyticsSerializer):
    title = serializers.CharField()
    description = serializers.CharField()
    seller_id = serializers.IntegerField()

    class Meta:
        model = ShopAnalytics
        fields = [
            "total_products",
            "total_orders",
            "total_reviews",
            "rating",
            "score",
            "daily_position",
        ] + ["title", "description", "seller_id"]
