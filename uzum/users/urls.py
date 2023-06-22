from django.urls import path

from uzum.users.views import (
    CodeVerificationView,
    VerificationSendView,
    user_detail_view,
    user_redirect_view,
    user_update_view,
)

app_name = "users"
urlpatterns = [
    path("~redirect/", view=user_redirect_view, name="redirect"),
    path("~update/", view=user_update_view, name="update"),
    path("phone/send/", view=VerificationSendView.as_view(), name="send_verification"),
    path("phone/verify/", view=CodeVerificationView.as_view(), name="verify_code"),
    path("<str:username>/", view=user_detail_view, name="detail"),
]
