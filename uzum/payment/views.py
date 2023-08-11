from payme.views import MerchantAPIView
from rest_framework.views import APIView
from rest_framework.response import Response

from uzum.payment.serializers import GeneratePayLinkSerializer

from payme.methods.generate_link import GeneratePayLink


class PaymeCallBackAPIView(MerchantAPIView):
    def create_transaction(self, order_id, action, *args, **kwargs) -> None:
        print(f"create_transaction for order_id: {order_id}, response: {action}")

    def perform_transaction(self, order_id, action, *args, **kwargs) -> None:
        print(f"perform_transaction for order_id: {order_id}, response: {action}")

    def cancel_transaction(self, order_id, action, *args, **kwargs) -> None:
        print(f"cancel_transaction for order_id: {order_id}, response: {action}")


class GeneratePayLinkAPIView(APIView):
    def post(self, request, *args, **kwargs):
        """
        Generate a payment link for the given order ID and amount.

        Request parameters:
            - order_id (int): The ID of the order to generate a payment link for.
            - amount (int): The amount of the payment.

        Example request:
            curl -X POST \
                'http://your-host/shop/pay-link/' \
                --header 'Content-Type: application/json' \
                --data-raw '{
                "order_id": 999,
                "amount": 999
            }'

        Example response:
            {
                "pay_link": "http://payme-api-gateway.uz/bT0jcmJmZk1vNVJPQFFoP05GcHJtWnNHeH"
            }
        """
        serializer = GeneratePayLinkSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        pay_link = GeneratePayLink(**serializer.validated_data).generate_link()

        return Response({"pay_link": pay_link})
