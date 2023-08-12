import json

from django.utils.timezone import datetime as dt
from django.utils.timezone import make_aware

from config.settings.base import env
from uzum.payment.exceptions import PerformTransactionDoesNotExist
from uzum.payment.models import Order


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
            raise PerformTransactionDoesNotExist() from error

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
