from django.urls import path
from django.views.decorators.cache import cache_page

from uzum.category.utils import seconds_until_next

from .views import BannerImpactView, BannersView, OngoingBannersView

app_name = "banner"

urlpatterns = [
    path("", BannersView.as_view(), name="banners"),
    path("impact/<int:product_id>/", BannerImpactView.as_view(), name="banner-impact"),
]
