from rest_framework import serializers

from uzum.review.models import PopularSeaches


class PopularSearchesSerializer(serializers.ModelSerializer):
    class Meta:
        model = PopularSeaches
        fields = ["words", "requests_count", "created_at", "date_pretty"]
