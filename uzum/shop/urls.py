# urls.py
from django.urls import path
from django.views.decorators.cache import cache_page

from uzum.category.utils import seconds_until_next

from . import views

app_name = "shops"
urlpatterns = [
    path("", views.ShopsView.as_view(), name="all-shops"),
    path("select/", views.AllShopsView.as_view(), name="all-shops-select"),
    path("current/<str:link>", views.CurrentShopView.as_view(), name="all-shops"),
    path("treemap/", views.TreemapShopsView.as_view(), name="all-shops"),
    path(
        "segmentation/orders/",
        cache_page(seconds_until_next())(views.ShopsOrdersSegmentationView.as_view()),
        name="all-shops",
    ),
    path(
        "segmentation/products/",
        cache_page(seconds_until_next())(views.ShopsProductsSegmentation.as_view()),
        name="all-shops",
    ),
    path("analytics/<int:seller_id>/", views.ShopAnalyticsView.as_view(), name="all-shops"),
    path("analytics/daily/<int:seller_id>/", views.ShopDailySalesView.as_view(), name="all-shops"),
    path("competitors/<int:seller_id>/", views.ShopCompetitorsView.as_view(), name="all-shops"),
    path(
        "products/category/<int:seller_id>/<int:category_id>/",
        views.ShopProductsByCategoryView.as_view(),
        name="shop-products",
    ),
    path("products/<int:seller_id>/", views.ShopProductsView.as_view(), name="shop-products"),
    path("products/tops/<int:seller_id>/", views.ShopTopProductsView.as_view(), name="shop-top-products"),
    path("products/stopped/<int:seller_id>/", views.StoppedProductsView.as_view(), name="shop-top-products"),
    path("categories/<int:seller_id>/", views.ShopCategoriesView.as_view(), name="shop-products"),
    path(
        "category/<int:seller_id>/<int:category_id>/", views.ShopCategoryAnalyticsView.as_view(), name="shop-products"
    ),
    path("top5/", views.Top5ShopsView.as_view(), name="top-shops"),
    path("yesterday-tops/", views.YesterdayTopsView.as_view(), name="yesterday-tops"),
]
