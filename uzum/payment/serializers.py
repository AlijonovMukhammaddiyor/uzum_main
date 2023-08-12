import logging

from django.conf import settings
from rest_framework import serializers

from config.settings.base import env
from uzum.payment.exceptions import IncorrectAmount, PerformTransactionDoesNotExist
from uzum.payment.models import MerchatTransactionsModel, Order
from uzum.payment.utils import get_params

logger = logging.getLogger(__name__)


class MerchatTransactionsModelSerializer(serializers.ModelSerializer):
    """
    MerchatTransactionsModelSerializer class \
        That's used to serialize merchat transactions data.
    """

    start_date = serializers.IntegerField(allow_null=True)
    end_date = serializers.IntegerField(allow_null=True)

    class Meta:
        # pylint: disable=missing-class-docstring
        model: MerchatTransactionsModel = MerchatTransactionsModel
        fields: str = "__all__"
        extra_fields = ["start_date", "end_date"]

    def validate(self, attrs) -> dict:
        """
        Validate the data given to the MerchatTransactionsModel.
        """
        order = attrs.get("order")
        if order is not None:
            if isinstance(order, int):
                try:
                    order = Order.objects.get(order_id=order)
                except Order.DoesNotExist as error:
                    logger.error("Order does not exist order_id: %s", order)
                    raise PerformTransactionDoesNotExist() from error
            try:
                if order.amount != int(attrs["amount"]):
                    raise IncorrectAmount()

            except IncorrectAmount as error:
                logger.error("Invalid amount for order: %s", attrs["order"])
                raise IncorrectAmount() from error

        return attrs

    def validate_amount(self, amount) -> int:
        """
        Validator for Transactions Amount.
        """
        logger.info("Validating amount: %s", amount)
        if amount is None:
            raise IncorrectAmount()

        if int(amount) <= env.int("PAYME_MIN_AMOUNT"):
            raise IncorrectAmount("Payment amount is less than allowed.")

        return amount

    def validate_order_id(self, order_id) -> int:
        """
        Use this method to check if a transaction is allowed to be executed.

        Parameters
        ----------
        order_id: str -> Order Indentation.
        """
        try:
            logger.info("Order id: %s", order_id)
            Order.objects.get(order_id=order_id)
        except Order.DoesNotExist as error:
            logger.error("Order does not exist order_id: %s", order_id)
            raise PerformTransactionDoesNotExist() from error

        return order_id

    @staticmethod
    def get_validated_data(params: dict) -> dict:
        """
        This static method helps to get validated data.

        Parameters
        ----------
        params: dict — Includes request params.
        """
        serializer = MerchatTransactionsModelSerializer(data=get_params(params))
        serializer.is_valid(raise_exception=True)
        clean_data: dict = serializer.validated_data

        return clean_data


class GeneratePayLinkSerializer(serializers.Serializer):
    order_id = serializers.IntegerField()
    amount = serializers.IntegerField()
