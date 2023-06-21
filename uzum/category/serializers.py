from rest_framework.serializers import ModelSerializer

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
