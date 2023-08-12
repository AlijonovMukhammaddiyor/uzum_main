import datetime
import logging
import time
import uuid

from uzum.payment.exceptions import TooManyRequests
from uzum.payment.models import MerchatTransactionsModel, Order
from uzum.payment.serializers import MerchatTransactionsModelSerializer
from uzum.payment.utils import get_params
from uzum.users.models import User

logger = logging.getLogger(__name__)


class CreateTransaction:
    """
    CreateTransaction class
    That's used to create transaction

    Full method documentation
    -------------------------
    https://developer.help.paycom.uz/metody-merchant-api/createtransaction
    """

    def __call__(self, params: dict) -> dict:
        logger.info("Create transaction method called")
        serializer = MerchatTransactionsModelSerializer(data=get_params(params))
        serializer.is_valid(raise_exception=True)
        order = serializer.validated_data.get("order")
        user = serializer.validated_data.get("user")

        try:
            transaction = MerchatTransactionsModel.objects.filter(order=order).last()

            if transaction is not None:
                if transaction._id != serializer.validated_data.get("_id"):
                    raise TooManyRequests()

        except TooManyRequests as error:
            logger.error("Too many requests for transaction %s", error)
            raise TooManyRequests() from error

        if transaction is None:
            try:
                transaction, _ = MerchatTransactionsModel.objects.get_or_create(
                    _id=serializer.validated_data.get("_id"),
                    order=order,
                    amount=serializer.validated_data.get("amount"),
                    created_at_ms=int(time.time() * 1000),
                    user=user,
                )
            except Order.DoesNotExist as error:
                logger.error("Order %s does not exist", error)
                raise Order.DoesNotExist() from error
            except User.DoesNotExist as error:
                logger.error("User %s does not exist", error)
                raise User.DoesNotExist() from error

        if transaction:
            response: dict = {
                "result": {
                    "create_time": int(transaction.created_at_ms),
                    "transaction": transaction.transaction_id,
                    "state": int(transaction.state),
                }
            }

        return order.order_id, response

    @staticmethod
    def _convert_ms_to_datetime(time_ms: str) -> int:
        """Use this format to convert from time ms to datetime format."""
        readable_datetime = datetime.datetime.fromtimestamp(time_ms / 1000)

        return readable_datetime
