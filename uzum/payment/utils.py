import json
import logging
from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

from django.utils.timezone import datetime as dt
from django.utils.timezone import make_aware

from config.settings.base import env
from uzum.payment.exceptions import PerformTransactionDoesNotExist
from uzum.payment.models import ENTERPRISE, PREMIUM, PRO, Order

logger = logging.getLogger(__name__)


def get_params(params: dict) -> dict:
    """
    Use this function to get the parameters from the payme.
    """
    account: dict = params.get("account")

    clean_params: dict = {}
    clean_params["_id"] = params.get("id")
    clean_params["time"] = params.get("time")
    clean_params["amount"] = params.get("amount")
    clean_params["reason"] = params.get("reason")

    # get statement method params
    clean_params["start_date"] = params.get("from")
    clean_params["end_date"] = params.get("to")

    if account is not None:
        account_name: str = env.str("PAYME_ACCOUNT")
        # clean_params["order_id"] = account[account_name]
        order_id = account.get(account_name)
        try:
            order = Order.objects.get(order_id=order_id)
            clean_params["order"] = order.order_id
            clean_params["user"] = order.user.id
        except Order.DoesNotExist as error:
            logger.error(f"Order with order_id: {order_id} does not exist")
            raise PerformTransactionDoesNotExist() from error

    logger.info(f"Clean params: {clean_params}")

    return clean_params


def make_aware_datetime(start_date: int, end_date: int):
    """
    Convert Unix timestamps to aware datetimes.

    :param start_date: Unix timestamp (milliseconds)
    :param end_date: Unix timestamp (milliseconds)

    :return: A tuple of two aware datetimes
    """
    return map(lambda timestamp: make_aware(dt.fromtimestamp(timestamp / 1000)), [start_date, end_date])


def to_json(**kwargs) -> dict:
    """
    Use this static method to data dumps.
    """
    data: dict = {
        "method": kwargs.pop("method"),
        "params": kwargs.pop("params"),
    }

    return json.dumps(data)


def getPackageType(amount):
    """
    Args:
        amount (_type_): amount in tiyin
    """
    return "Pullik Tarif"


def next_payment_date(start_date, months=1):
    if months == 1 or months == 3:
        return start_date + relativedelta(months=months)
    else:
        raise ValueError("Invalid period. Accepts only '1 month' or '3 months'.")
