import datetime

import pytz
from rest_framework.request import Request

from uzum.users.models import User


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
    return datetime.datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")


def get_today_pretty_fake():
    # check if it is 7:00 AM in Tashkent
    if datetime.datetime.now(tz=pytz.timezone("Asia/Tashkent")).hour >= 7:
        return datetime.datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")
    else:
        # if not, return yesterday
        return (datetime.datetime.now(tz=pytz.timezone("Asia/Tashkent")) - datetime.timedelta(days=1)).strftime(
            "%Y-%m-%d"
        )


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


def check_user(request: Request):
    try:
        user: User = request.user
        if request.user.is_authenticated:
            if user.is_pro or user.is_proplus:
                return user

        return None
    except Exception as e:
        print("Error in check_user: ", e)
        return None
