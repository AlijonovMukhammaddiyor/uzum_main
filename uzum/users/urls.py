from django.urls import path

from uzum.users.views import (  # CodeVerificationView,; VerificationSendView,
    GoogleView,
    PasswordRenewView,
    SetShopsView,
    user_detail_view,
    user_redirect_view,
    user_update_view,
    AddfavouriteProductView,
    AddfavouriteShopView,
    RemovefavouriteProductView,
    RemovefavouriteShopView,
    GetFavouriteProductsView,
    GetFavouriteShopsView,
    TelegramBotView,
)

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    # path("phone/send/", view=VerificationSendView.as_view(), name="send_verification"),
    # path("phone/verify/", view=CodeVerificationView.as_view(), name="verify_code"),
    path("set-shops/", view=SetShopsView.as_view(), name="set_shops"),
    path("shops/add", view=AddfavouriteShopView.as_view(), name="add_shop"),
    path("shops/remove", view=RemovefavouriteShopView.as_view(), name="remove_shop"),
    path("shops/get", view=GetFavouriteShopsView.as_view(), name="get_shops"),
    path("products/add", view=AddfavouriteProductView.as_view(), name="add_product"),
    path("products/remove", view=RemovefavouriteProductView.as_view(), name="remove_product"),
    path("products/get", view=GetFavouriteProductsView.as_view(), name="get_products"),
    path("telegram-connect/", view=TelegramBotView.as_view(), name="reports"),
    path("<str:username>/", view=user_detail_view, name="detail"),
]
