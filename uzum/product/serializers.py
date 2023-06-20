from rest_framework import serializers

from uzum.sku.serializers import ExtendedSkuSerializer

from .models import Product, ProductAnalytics


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
    position = serializers.IntegerField(read_only=True)
    score = serializers.FloatField(read_only=True)
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
        fields = "__all__"
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
            "title",
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
