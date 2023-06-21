# urls.py
from django.urls import path
from django.views.decorators.cache import cache_page
from uzum.category.utils import seconds_until_midnight

from . import views

app_name = "category"
urlpatterns = [
    path("", cache_page(seconds_until_midnight())(views.CategoryTreeView.as_view()), name="all-categories"),
    path(
        "products/<int:category_id>",
        cache_page(seconds_until_midnight())(views.CategoryProductsView.as_view()),
        name="category-products",
    ),
    path(
        "products/comparison/<int:category_id>",
        cache_page(seconds_until_midnight())(views.CategoryProductsPeriodComparisonView.as_view()),
        name="category-products",
    ),
    path(
        "analytics/<int:category_id>",
        cache_page(seconds_until_midnight())(views.CategoryDailyAnalyticsView.as_view()),
        name="category-products",
    ),
    path("analytics/subcategory/<int:category_id>", views.SubcategoriesView.as_view(), name="category-products"),
    path(
        "analytics/segmentation/<int:category_id>",
        cache_page(seconds_until_midnight())(views.CategoryPriceSegmentationView.as_view()),
        name="category-products",
    ),
    path(
        "analytics/shops/<int:category_id>",
        cache_page(seconds_until_midnight())(views.CategoryShopsView.as_view()),
        name="category-products",
    ),
]
