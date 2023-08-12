from django.urls import path

from uzum.payment.views import MerchantAPIView

app_name = "payment"

urlpatterns = [
    # path('pay-link/', GeneratePayLinkAPIView.as_view(), name='generate-pay-link')
    path("merchant/", MerchantAPIView.as_view(), name="merchant")
]
