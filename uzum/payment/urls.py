from django.urls import path

from uzum.payment.views import GeneratePayLinkAPIView, MerchantAPIView

app_name = "payment"

urlpatterns = [
    path("paylink/", GeneratePayLinkAPIView.as_view(), name="generate-pay-link"),
    path("merchant/", MerchantAPIView.as_view(), name="merchant"),
]
