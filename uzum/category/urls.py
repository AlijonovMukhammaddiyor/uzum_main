# urls.py
from django.urls import path

from . import views

app_name = "category"
urlpatterns = [
    path("", views.CategoryTreeView.as_view(), name="all-categories"),
    path("products/<int:category_id>", views.CategoryProductsView.as_view(), name="category-products"),
    path(
        "products/comparison/<int:category_id>",
        views.CategoryProductsPeriodComparisonView.as_view(),
        name="category-products",
    ),
    path("analytics/<int:category_id>", views.CategoryDailyAnalyticsView.as_view(), name="category-products"),
    path("analytics/subcategory/<int:category_id>", views.SubcategoriesView.as_view(), name="category-products"),
    path(
        "analytics/segmentation/<int:category_id>",
        views.CategoryPriceSegmentationView.as_view(),
        name="category-products",
    ),
    path(
        "analytics/shops/<int:category_id>",
        views.CategoryShopsView.as_view(),
        name="category-products",
    ),
]
