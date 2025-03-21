from rest_framework import serializers

from .models import Badge


class BadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = "__all__"
        read_only_fields = (
            "badge_id",
            "created_at",
        )


class ProductBadgeSerializer(serializers.ModelSerializer):
    class Meta:
        model = Badge
        fields = ["background_color", "text", "text_color"]
