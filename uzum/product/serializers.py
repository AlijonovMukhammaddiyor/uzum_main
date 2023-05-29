from rest_framework import serializers

from .models import Product, ProductAnalytics


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = "__all__"
        read_only_fields = ("product_id", "created_at", "updated_at")

    def create(self, validated_data):
        return Product.objects.create(**validated_data)


class ProductAnalyticsSerializer(serializers.ModelSerializer):
    class Meta:
        model = ProductAnalytics
        fields = "__all__"
        read_only_fields = ("id", "created_at", "date_pretty")

    def create(self, validated_data):
        return ProductAnalytics.objects.create(**validated_data)
