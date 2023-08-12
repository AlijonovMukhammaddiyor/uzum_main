import logging
import time

from django.db import DatabaseError

from uzum.payment.models import MerchatTransactionsModel
from uzum.payment.serializers import MerchatTransactionsModelSerializer
from uzum.payment.utils import get_params

logger = logging.getLogger(__name__)


class PerformTransaction:
    """
    PerformTransaction class
    That's used to perform a transaction.

    Full method documentation
    -------------------------
    https://developer.help.paycom.uz/metody-merchant-api/performtransaction
    """

    def __call__(self, params: dict) -> dict:
        serializer = MerchatTransactionsModelSerializer(data=get_params(params))
        serializer.is_valid(raise_exception=True)
        clean_data: dict = serializer.validated_data
        response: dict = None
        try:
            transaction = MerchatTransactionsModel.objects.get(
                _id=clean_data.get("_id"),
            )
            transaction.state = 2
            if transaction.perform_time == 0:
                transaction.perform_time = int(time.time() * 1000)

            transaction.save()
            response: dict = {
                "result": {
                    "perform_time": int(transaction.perform_time),
                    "transaction": transaction.transaction_id,
                    "state": int(transaction.state),
                }
            }
        except Exception as error:
            logger.error("error while getting transaction in db: %s", error)

        return transaction.order_id, response
