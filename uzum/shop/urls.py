# urls.py
from django.urls import path

from . import views

app_name = "shops"
urlpatterns = [
    path("", views.ShopsView.as_view(), name="all-shops"),
    path("segmentation/orders/", views.ShopsOrdersSegmentationView.as_view(), name="all-shops"),
    path("segmentation/products/", views.ShopsProductsSegmentation.as_view(), name="all-shops"),
    path("analytics/<int:seller_id>", views.ShopAnalyticsView.as_view(), name="all-shops"),
    path("competitors/<int:seller_id>", views.ShopCompetitorsView.as_view(), name="all-shops"),
    path(
        "products/category/<int:seller_id>/<int:category_id>",
        views.ShopProductsByCategoryView.as_view(),
        name="shop-products",
    ),
    path("products/<int:seller_id>", views.ShopProductsView.as_view(), name="shop-products"),
    path("categories/<int:seller_id>", views.ShopCategoryAnalyticsView.as_view(), name="shop-products"),
]
