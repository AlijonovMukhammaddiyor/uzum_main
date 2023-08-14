import logging

from uzum.payment.exceptions import IncorrectAmount
from uzum.payment.serializers import MerchatTransactionsModelSerializer
from uzum.payment.utils import get_params, getPackageType

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
        amount = params.get("amount")
        package = getPackageType(amount)
        if not package:
            package_string = "UzAnalitika - " + package
        else:
            package_string = "UzAnalitika - " + "Free"
        serializer = MerchatTransactionsModelSerializer(data=get_params(params))
        serializer.is_valid(raise_exception=True)

        response = {
            "result": {
                "allow": True,
                "detail": {
                    "receipt_type": 0,
                    "items": [
                        {
                            "title": "UzAnalitika - Pullik Tarif",
                            "price": amount,
                            "count": 1,
                            "code": "10602010001000000",
                            "vat_percent": 0,
                            "package_code": "1500416",
                        }
                    ],
                },
            }
        }

        return None, response
