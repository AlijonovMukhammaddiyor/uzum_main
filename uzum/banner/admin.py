from django.contrib import admin

from uzum.banner.models import Banner


# Register your models here.
@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "link",
        "typename",
        "created_at",
        "updated_at",
    )
    list_display_links = ("id", "link")
    list_filter = ("typename",)
    search_fields = ("link", "typename")
    list_per_page = 25
