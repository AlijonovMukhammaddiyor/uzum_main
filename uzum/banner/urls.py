from django.urls import path

from uzum.category.utils import seconds_until_midnight
from .views import BannerImpactView, BannersView, OngoingBannersView
from django.views.decorators.cache import cache_page


app_name = "banner"

urlpatterns = [
    path("", BannersView.as_view(), name="banners"),
    path("ongoing", cache_page(seconds_until_midnight())(OngoingBannersView.as_view()), name="ongoing-banners"),
    path(
        "<str:banner_id>",
        cache_page(seconds_until_midnight())(BannerImpactView.as_view()),
        # BannerImpactView.as_view(),
        name="ongoing-banners",
    ),
]
