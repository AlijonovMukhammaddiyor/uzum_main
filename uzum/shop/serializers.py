from rest_framework import serializers
from rest_framework.serializers import ModelSerializer

from .models import Shop, ShopAnalytics, ShopAnalyticsRecent


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

class ShopAnalyticsRecentSerializer(ModelSerializer):
    class Meta:
        model = ShopAnalyticsRecent
        fields = [
            "total_products",
            "total_orders",
            "total_reviews",
            "rating",
            "average_purchase_price",
            "monthly_revenue",
            "monthly_orders",
            "quarterly_revenue",
            "quarterly_orders",
            "title",
            "avatar",
            "link",
            "seller_id",
        ]

    def to_representation(self, instance):
        # Use the original to_representation to get the original serialized data
        representation = super().to_representation(instance)

        # Adjust the title
        representation["title"] = f'{representation["title"]}(({representation["link"]}))'

        return representation

class ShopAnalyticsSerializer(ModelSerializer):
    class Meta:
        model = ShopAnalytics
        fields = [
            "total_products",
            "total_orders",
            "total_reviews",
            "rating",
            "date_pretty",
            "position",
            "average_purchase_price",
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
        ] + ["title", "description", "seller_id"]
