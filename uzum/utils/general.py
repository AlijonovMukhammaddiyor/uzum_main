import datetime

import pytz
from django.db import models
from django.utils.translation import gettext_lazy as _
from rest_framework import status
from rest_framework.request import Request
from rest_framework.response import Response


class Tariffs(models.TextChoices):
    FREE = "free", _("Free")
    TRIAL = "trial", _("Trial")
    BASE = "base", _("Base")
    SELLER = "seller", _("Seller")
    BUSINESS = "business", _("Business")


def decode_request(request: Request, method: str) -> dict:
    """
    Decodes request body.
    Args:
        request (Request): _description_

    Returns:
        dict: decoded request body
    """
    if method == "GET":
        return request.query_params.dict()
    elif method == "POST":
        return request.data.dict()
    else:
        # just return empty dict
        return {}


def get_today_pretty():
    return "2023-10-19"
    # return datetime.datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")


def get_today_pretty_fake():
    # check if it is 7:00 AM in Tashkent
    return "2023-10-19"
    # if datetime.datetime.now(tz=pytz.timezone("Asia/Tashkent")).hour >= 23:
    #     return datetime.datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")
    # else:
    #     # if not, return yesterday
    #     return (datetime.datetime.now(tz=pytz.timezone("Asia/Tashkent")) - datetime.timedelta(days=1)).strftime(
    #         "%Y-%m-%d"
    #     )


def get_day_before_pretty(date_pretty: str):
    """
    Returns yesterday's date_pretty.
    Args:
        date_pretty (str): date_pretty in format %Y-%m-%d
    """
    try:
        date = datetime.datetime.strptime(date_pretty, "%Y-%m-%d").astimezone(pytz.timezone("Asia/Tashkent")).date()

        yesterday = date - datetime.timedelta(days=1)

        # Format yesterday's date as a string in 'YYYY-MM-DD' format
        yesterday_str = yesterday.strftime("%Y-%m-%d")

        return yesterday_str
    except Exception as e:
        print("Error in get_day_before: ", e)
        return None


def get_next_day_pretty(date_pretty):
    date = datetime.datetime.strptime(date_pretty, "%Y-%m-%d").astimezone(pytz.timezone("Asia/Tashkent")).date()
    next_day = date + datetime.timedelta(days=1)
    return next_day.strftime("%Y-%m-%d")


def get_start_date():
    # return the beginning of may 19 in Asia/Tashkent timezone
    return datetime.datetime(2019, 5, 19, tzinfo=pytz.timezone("Asia/Tashkent")).replace(hour=0, minute=0, second=0)


def get_end_of_day(date: datetime.datetime):
    return date.replace(hour=23, minute=59, second=59)


def get_start_of_day(date: datetime.datetime):
    return date.replace(hour=0, minute=0, second=0)


def date_in_Tashkent(date: datetime.datetime):
    return date.astimezone(pytz.timezone("Asia/Tashkent"))


def check_user_tariff(request: Request, tarif: Tariffs = Tariffs.FREE):
    """
    Checks if the user is authenticated and has the given tariff.
    Args:
        request (Request): _description_
    Returns:
    """
    try:
        user = request.user
        if not user:
            return None
        if request.user.is_authenticated:
            # if current time is after user.payment_date, set user.tariff to FREE
            if user.payment_date and user.payment_date < datetime.datetime.now(tz=pytz.timezone("Asia/Tashkent")):
                user.tariff = Tariffs.FREE
                user.save()
            if user.tariff == tarif:
                return True
            else:
                return False
        return None
    except Exception as e:
        print("Error in check_user: ", e)
        return None


def authorize_Base_tariff(request: Request):
    """
    Args:
        request (Request): _description_
    Returns:
    """
    try:
        if check_user_tariff(request) is None:
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"message": "Forbidden", "detail": "Only authorized users can access this endpoint"},
            )
        elif check_user_tariff(request, Tariffs.FREE) or check_user_tariff(request, Tariffs.TRIAL):
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"message": "Forbidden", "detail": "Free users can't access this endpoint"},
            )
    except Exception as e:
        print("Error in check_user: ", e)


def authorize_Seller_tariff(request: Request):
    """
    Args:
        request (Request): _description_
    Returns:
    """
    try:
        if check_user_tariff(request) is None:
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"message": "Forbidden", "detail": "Only authorized users can access this endpoint"},
            )
        elif (
            check_user_tariff(request, Tariffs.FREE)
            or check_user_tariff(request, Tariffs.TRIAL)
            or check_user_tariff(request, Tariffs.BASE)
        ):
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"message": "Forbidden", "detail": "Free or Basic users can't access this endpoint"},
            )
    except Exception as e:
        print("Error in check_user: ", e)


def authorize_Business_tariff(request: Request):
    """
    Args:
        request (Request): _description_
    Returns:
    """
    try:
        if check_user_tariff(request) is None:
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"message": "Forbidden", "detail": "Only authorized users can access this endpoint"},
            )
        elif (
            check_user_tariff(request, Tariffs.FREE)
            or check_user_tariff(request, Tariffs.TRIAL)
            or check_user_tariff(request, Tariffs.BASE)
            or check_user_tariff(request, Tariffs.SELLER)
        ):
            return Response(
                status=status.HTTP_403_FORBIDDEN,
                data={"message": "Forbidden", "detail": "Free, Basic, Seller users can't access this endpoint"},
            )
    except Exception as e:
        print("Error in check_user: ", e)


def get_days_based_on_tariff(user):
    try:
        tariff = user.tariff
        if tariff == Tariffs.FREE:
            return 3

        elif tariff == Tariffs.TRIAL:
            return 3

        elif tariff == Tariffs.BASE:
            return 60

        elif tariff == Tariffs.SELLER:
            return 90

        elif tariff == Tariffs.BUSINESS:
            return 120

    except Exception as e:
        print("Error in get_days_based_on_tariff: ", e)
        return 30
