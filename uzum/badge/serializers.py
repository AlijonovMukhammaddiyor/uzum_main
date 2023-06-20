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
