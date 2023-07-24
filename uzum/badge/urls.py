from django.urls import path
from django.views.decorators.cache import cache_page

from uzum.category.utils import seconds_until_next

from . import views

app_name = "badges"

urlpatterns = [
    path("", cache_page(seconds_until_next())(views.AllBadgesView.as_view()), name="all-badges"),
    path("ongoing", cache_page(seconds_until_next())(views.OngoingBadgesView.as_view()), name="all-badges"),
    path(
        "<int:badge_id>/products",
        cache_page(seconds_until_next())(views.BadgeProducts.as_view()),
        name="all-badges",
    ),
    path(
        "<int:badge_id>/analytics",
        cache_page(seconds_until_next())(views.BadgeAnalytics.as_view()),
        name="all-badges",
    ),
    path("seaches/", views.PopularWordsView.as_view(), name="popular-searches"),
]
