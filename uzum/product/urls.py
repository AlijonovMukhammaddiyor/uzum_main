from django.urls import path

from . import views

app_name = "products"
urlpatterns = [
    path("", views.ProductsView.as_view(), name="all-products"),
    path("segmentation", views.ProductsSegmentationView.as_view(), name="all-products"),
    path("analytics/<int:product_id>", views.ProductAnalyticsView.as_view(), name="all-products"),
    path("similar/<int:product_id>", views.SimilarProductsViewByUzum.as_view(), name="all-products"),
    # path("similar/content/<int:product_id>", views.ProductReviews.as_view(), name="all-products"),
    path("reviews/<int:product_id>", views.ProductReviews.as_view(), name="all-products"),
]
