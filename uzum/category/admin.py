from django.contrib import admin

from uzum.category.models import Category, CategoryAnalytics


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "categoryId",
        "parent",
        "adult",
        "created_at",
        "updated_at",
        "get_children",
    )
    list_filter = ("parent", "adult", "created_at", "updated_at", "categoryId")
    search_fields = ("title", "categoryId")

    def get_children(self, obj):
        if obj.children.all():
            return list(obj.children.all().values_list("title", flat=True))
        else:
            return "NA"


@admin.register(CategoryAnalytics)
class CategoryAnalyticsAdmin(admin.ModelAdmin):
    list_display = ("category", "totalProducts", "created_at")
    list_filter = ("category", "totalProducts", "created_at")
    search_fields = ("category", "totalProducts", "created_at")
