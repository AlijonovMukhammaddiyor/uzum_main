from django.contrib import admin

from uzum.campaign.models import Campaign


# Register your models here.
@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "offer_id",
        "typename",
        "created_at",
        "updated_at",
    )
    list_display_links = ("id", "title")
    list_filter = ("offer_id", "typename")
    search_fields = ("title", "typename")
    list_per_page = 25
    ordering = ("offer_id", "id")
