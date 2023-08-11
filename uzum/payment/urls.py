from django.urls import path

from uzum.payment.views import PaymeCallBackAPIView

app_name = "payment"

urlpatterns = [
    # path('pay-link/', GeneratePayLinkAPIView.as_view(), name='generate-pay-link')
    path("callback/", PaymeCallBackAPIView.as_view(), name="callback")
]
