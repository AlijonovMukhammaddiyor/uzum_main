from django.urls import path
from django.views.decorators.cache import cache_page

from uzum.category.utils import seconds_until_midnight

from . import views

app_name = "badges"

urlpatterns = [
    path("", cache_page(seconds_until_midnight())(views.AllBadgesView.as_view()), name="all-badges"),
    path("ongoing", cache_page(seconds_until_midnight())(views.OngoingBadgesView.as_view()), name="all-badges"),
    path(
        "<int:badge_id>/products",
        cache_page(seconds_until_midnight())(views.BadgeProducts.as_view()),
        name="all-badges",
    ),
    path(
        "<int:badge_id>/analytics",
        cache_page(seconds_until_midnight())(views.BadgeAnalytics.as_view()),
        name="all-badges",
    ),
    path("seaches/", views.PopularWordsView.as_view(), name="popular-searches"),
]
