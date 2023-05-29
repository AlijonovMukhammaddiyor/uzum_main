from rest_framework.serializers import ModelSerializer

from .models import Category, CategoryAnalytics


class CategorySerializer(ModelSerializer):
    class Meta:
        model = Category
        fields = "__all__"
        depth = 1


class CategoryAnalytics(ModelSerializer):
    class Meta:
        model = CategoryAnalytics
        fields = "__all__"
        depth = 1
