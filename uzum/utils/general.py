import datetime

import pytz
from rest_framework.request import Request


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
