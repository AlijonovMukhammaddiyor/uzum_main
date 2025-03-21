import datetime
import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from config.settings.base import env
from uzum.payment.methods.generate_link import GeneratePayLink
from uzum.payment.models import Order
from uzum.payment.serializers import GeneratePayLinkSerializer
from uzum.payment.utils import next_payment_date
from uzum.users.models import User
from uzum.utils.general import Tariffs

logger = logging.getLogger(__name__)


import base64
import binascii

from rest_framework.exceptions import ValidationError

from uzum.payment.exceptions import (MethodNotFound,
                                     PerformTransactionDoesNotExist,
                                     PermissionDenied)
from uzum.payment.methods.cancel_transaction import CancelTransaction
from uzum.payment.methods.check_perform_transaction import \
    CheckPerformTransaction
from uzum.payment.methods.check_transaction import CheckTransaction
from uzum.payment.methods.create_transaction import CreateTransaction
from uzum.payment.methods.get_statement import GetStatement
from uzum.payment.methods.perform_transaction import PerformTransaction


class MerchantAPIView(APIView):
    """
    MerchantAPIView class provides payme call back functionality.
    """

    permission_classes = ()
    authentication_classes = ()

    def post(self, request) -> Response:
        """
        Payme sends post request to our call back url.
        That methods are includes 5 methods
            - CheckPerformTransaction
            - CreateTransaction
            - PerformTransaction
            - CancelTransaction
            - CheckTransaction
            - GetStatement
        """
        password = request.META.get("HTTP_AUTHORIZATION")
        if self.authorize(password):
            incoming_data: dict = request.data
            incoming_method: str = incoming_data.get("method")

            logger.info("Call back data is incoming %s", incoming_data)

            try:
                paycom_method = self.get_paycom_method_by_name(incoming_method=incoming_method)
            except ValidationError as error:
                logger.error("Validation Error occurred: %s", error)
                raise MethodNotFound() from error

            except PerformTransactionDoesNotExist as error:
                logger.error("PerformTransactionDoesNotExist Error occurred: %s", error)
                raise PerformTransactionDoesNotExist() from error

            order_id, action = paycom_method(incoming_data.get("params"))

        if isinstance(paycom_method, CreateTransaction):
            self.create_transaction(
                order_id=order_id,
                action=action,
            )

        if isinstance(paycom_method, PerformTransaction):
            self.perform_transaction(
                order_id=order_id,
                action=action,
            )

        if isinstance(paycom_method, CancelTransaction):
            self.cancel_transaction(
                order_id=order_id,
                action=action,
            )

        return Response(data=action)

    def get_paycom_method_by_name(self, incoming_method: str) -> object:
        """
        Use this static method to get the paycom method by name.
        :param incoming_method: string -> incoming method name
        """
        available_methods: dict = {
            "CheckPerformTransaction": CheckPerformTransaction,
            "CreateTransaction": CreateTransaction,
            "PerformTransaction": PerformTransaction,
            "CancelTransaction": CancelTransaction,
            "CheckTransaction": CheckTransaction,
            "GetStatement": GetStatement,
        }

        try:
            merchant_method = available_methods[incoming_method]
        except Exception as error:
            error_message = "Unavailable method: %s", incoming_method
            logger.error(error_message)
            raise MethodNotFound(error_message=error_message) from error

        merchant_method = merchant_method()

        return merchant_method

    @staticmethod
    def authorize(password: str) -> None:
        """
        Authorize the Merchant.
        :param password: string -> Merchant authorization password
        """
        is_payme: bool = False
        error_message: str = ""

        if not isinstance(password, str):
            error_message = "Request from an unauthorized source!"
            logger.error(error_message)
            raise PermissionDenied(error_message=error_message)

        password = password.split()[-1]

        try:
            password = base64.b64decode(password).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as error:
            error_message = "Error when authorize request to merchant!"
            logger.error(error_message)

            raise PermissionDenied(error_message=error_message) from error

        merchant_key = password.split(":")[-1]
        logger.info("Merchant key is %s", merchant_key)
        if merchant_key == env.str("PAYME_KEY"):
            is_payme = True

        if merchant_key != env.str("PAYME_KEY"):
            logger.error("Invalid key in request!")

        if is_payme is False:
            raise PermissionDenied(error_message="Unavailable data for unauthorized users!")

        return is_payme

    def create_transaction(self, order_id, action) -> None:
        """
        need implement in your view class
        """
        order = Order.objects.get(order_id=order_id)
        order.status = 2  # 2 - created
        order.save()
        logger.info(f"create_transaction for order_id: {order_id}, response: {action}")

    def perform_transaction(self, order_id, action) -> None:
        """
        need implement in your view class
        """
        order = Order.objects.get(order_id=order_id)
        order.status = 3  # 3 - performed
        order.save()

        # now update user tariff
        user: User = order.user
        months = order.months
        tariff = order.tariff
        user.tariff = tariff
        user.payment_date = next_payment_date(datetime.datetime.now(), months)

        user.save()
        try:
            user.is_paid = True
            user.save()
        except Exception as e:
            logger.error("Error in perform_transaction is paid: ", e)
        logger.info(f"perform_transaction for order_id: {order_id}, response: {action}")

    def cancel_transaction(self, order_id, action) -> None:
        """
        need implement in your view class
        """
        order = Order.objects.get(order_id=order_id)
        order.status = 4  # 4 - canceled
        order.save()
        logger.info(f"cancel_transaction for order_id: {order_id}, response: {action}")


class GeneratePayLinkAPIView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]

    def post(self, request, *args, **kwargs):
        """
        Generate a payment link for the given amount.

        Example response:
            {
                "pay_link": "http://payme-api-gateway.uz/bT0jcmJmZk1vNVJPQFFoP05GcHJtWnNHeH"
            }
        """
        user = request.user
        amount = request.data.get("amount")
        tariff = request.data.get("tariff")
        months = request.data.get("months")

        if not months:
            return Response({"months": "Months is required"}, status=400)

        if tariff != "free" and tariff != "seller" and tariff != "base" and tariff != "business":
            return Response({"tariff": "Tariff is not valid"}, status=400)

        if tariff == "free":
            tariff = Tariffs.FREE
        elif tariff == "seller":
            tariff = Tariffs.SELLER
        elif tariff == "base":
            tariff = Tariffs.BASE
        elif tariff == "business":
            tariff = Tariffs.BUSINESS

        if not amount:
            return Response({"amount": "Amount is required"}, status=400)

        amount *= 100  # convert to tiyin
        order = Order.objects.create(user=user, amount=amount, tariff=tariff, months=months)
        serializer = GeneratePayLinkSerializer(data={"order_id": order.order_id, "amount": amount})
        serializer.is_valid(raise_exception=True)
        pay_link = GeneratePayLink(**serializer.validated_data).generate_link()

        return Response({"pay_link": pay_link})
