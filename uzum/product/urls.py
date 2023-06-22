from django.urls import path
from django.views.decorators.cache import cache_page

from uzum.category.utils import seconds_until_midnight

from . import views

app_name = "products"
urlpatterns = [
    path("", views.ProductsView.as_view(), name="all-products"),
    path(
        "segmentation",
        cache_page(seconds_until_midnight())(views.ProductsSegmentationView.as_view()),
        name="segmentation",
    ),
    path(
        "analytics/<int:product_id>",
        views.ProductAnalyticsView.as_view(),
        name="product-analytics",
    ),
    path(
        "similar/<int:product_id>",
        views.SimilarProductsViewByUzum.as_view(),
        name="similar-products",
    ),
    # path("similar/content/<int:product_id>", views.ProductReviews.as_view(), name="all-products"),
    path("reviews/<int:product_id>", views.ProductReviews.as_view(), name="product-reviews"),
    path("seaches", views.PopularWords.as_view(), name="popular-searches"),
]
