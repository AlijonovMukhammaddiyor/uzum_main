from django.urls import path
from . import views

app_name = "badges"

urlpatterns = [
    path("", views.AllBadgesView.as_view(), name="all-badges"),
    path("ongoing", views.OngoingBadgesView.as_view(), name="all-badges"),
    path("<int:badge_id>/products", views.BadgeProducts.as_view(), name="all-badges"),
    path("<int:badge_id>/analytics", views.BadgeAnalytics.as_view(), name="all-badges"),
]
