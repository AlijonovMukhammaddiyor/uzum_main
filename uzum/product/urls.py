from django.urls import path
from django.views.decorators.cache import cache_page

from uzum.category.utils import seconds_until_next

from . import views

app_name = "products"
urlpatterns = [
    path("", views.ProductsView.as_view(), name="all-products"),
    path("<int:product_id>/", views.ProductView.as_view(), name="all-products"),
    path("current/<int:product_id>/", views.CurrentProductView.as_view(), name="current-product"),
    path(
        "segments/",
        cache_page(seconds_until_next())(views.AllProductsPriceSegmentationView.as_view()),
        # views.AllProductsPriceSegmentationView.as_view(),
        name="segmentation",
    ),
    path(
        "analytics/<int:product_id>/",
        views.SingleProductAnalyticsView.as_view(),
        name="product-analytics",
    ),
    path(
        "similar/<int:product_id>/",
        views.SimilarProductsViewByUzum.as_view(),
        name="similar-products",
    ),
    # path("similar/content/<int:product_id>", views.ProductReviews.as_view(), name="all-products"),
    path("reviews/<int:product_id>", views.ProductReviews.as_view(), name="product-reviews"),
    path("top/", views.Top5ProductsView.as_view(), name="top-products"),
    path("recent/", (views.NewProductsView.as_view()), name="new-products"),
    path("growing/", (views.GrowingProductsView.as_view()), name="growing-products"),
]
