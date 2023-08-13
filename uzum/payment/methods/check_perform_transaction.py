import logging

from uzum.payment.serializers import MerchatTransactionsModelSerializer
from uzum.payment.utils import get_params

logger = logging.getLogger(__name__)


class CheckPerformTransaction:
    """
    CheckPerformTransaction class
    That's used to check perform transaction.

    Full method documentation
    -------------------------
    https://developer.help.paycom.uz/metody-merchant-api/checktransaction
    """

    def __call__(self, params: dict) -> dict:
        logger.info("CheckPerformTransaction method called")
        serializer = MerchatTransactionsModelSerializer(data=get_params(params))
        serializer.is_valid(raise_exception=True)

        response = {
            "result": {
                "allow": True,
            }
        }

        return None, response
