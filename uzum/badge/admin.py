from django.contrib import admin

from uzum.badge.models import Badge


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    list_display = ("badge_id", "text", "description", "link", "created_at")
    list_display_links = ("badge_id", "text")
    search_fields = ("badge_id",)
    list_per_page = 25
