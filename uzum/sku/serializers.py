from rest_framework import serializers

from uzum.sku.models import Sku, SkuAnalytics


class SkuSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sku
        fields = [
            "sku",
            "product",
            "created_at",
            "updated_at",
            "barcode",
            "charity_profit",
            "discount_badge",
            "payment_per_month",
            "vat_amount",
            "vat_price",
            "vat_rate",
            "video_url",
            "characteristics",
        ]
        depth = 1


class SkuAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = SkuAnalytics
        fields = [
            "id",
            # "sku",
            "created_at",
            "available_amount",
            "orders_amount",
            "purchase_price",
            "full_price",
            "date_pretty",
        ]
        depth = 1


class ExtendedSkuSerializer(serializers.ModelSerializer):
    recent_analytics = SkuAnalyticsSerializer(many=True, read_only=True)

    class Meta:
        model = Sku
        fields = [
            "sku",
            "barcode",
            "charity_profit",
            "payment_per_month",
            "vat_amount",
            "vat_price",
            "vat_rate",
            "recent_analytics",
            "characteristics",
        ]
