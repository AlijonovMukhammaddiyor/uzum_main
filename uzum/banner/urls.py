from django.urls import path
from django.views.decorators.cache import cache_page

from uzum.category.utils import seconds_until_next

from .views import BannerImpactView, BannersView, OngoingBannersView

app_name = "banner"

urlpatterns = [
    path("", BannersView.as_view(), name="banners"),
    path("ongoing", cache_page(seconds_until_next())(OngoingBannersView.as_view()), name="ongoing-banners"),
    path(
        "<str:banner_id>",
        cache_page(seconds_until_next())(BannerImpactView.as_view()),
        # BannerImpactView.as_view(),
        name="ongoing-banners",
    ),
]
