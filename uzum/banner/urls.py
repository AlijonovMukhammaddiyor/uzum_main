from django.urls import path
from .views import BannersView, OngoingBannersView

app_name = "banner"

urlpatterns = [
    path("", BannersView.as_view(), name="banners"),
    path("ongoing", OngoingBannersView.as_view(), name="banners"),
]
