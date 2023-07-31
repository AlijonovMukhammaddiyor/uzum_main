# urls.py
from django.urls import path
from django.views.decorators.cache import cache_page

from uzum.category.utils import seconds_until_next

from . import views

app_name = "category"
urlpatterns = [
    path("", (views.CategoryTreeView.as_view()), name="all-categories"),
    path("current/<int:category_id>/", views.CurrentCategoryView.as_view(), name="current-categories"),
    path("segmentation/", views.AllCategoriesSegmentation.as_view(), name="segmentation"),
    path(
        "products/<int:category_id>/",
        views.CategoryProductsView.as_view(),
        name="category-products",
    ),
    path(
        "products/top/<int:category_id>/",
        views.CategoryTopProductsView.as_view(),
        name="category-products",
    ),
    path(
        "products/comparison/<int:category_id>/",
        views.CategoryProductsPeriodComparisonView.as_view(),
        name="category-products",
    ),
    path(
        "analytics/<int:category_id>/",
        views.CategoryDailyAnalyticsView.as_view(),
        name="category-products",
    ),
    path("analytics/subcategory/<int:category_id>/", views.SubcategoriesView.as_view(), name="category-products"),
    path(
        "analytics/segmentation/<int:category_id>/",
        views.CategoryPriceSegmentationView.as_view(),
        name="category-products",
    ),
    path(
        "analytics/shops/<int:category_id>/",
        views.CategoryShopsView.as_view(),
        name="category-products",
    ),
    path("niches/", views.NicheSlectionView.as_view(), name="niches"),
    path("growing/", views.GrowingCategoriesView.as_view(), name="growing-categories"),
    path("main/", views.MainCategoriesAnalyticsView.as_view(), name="growing-categories"),
]
