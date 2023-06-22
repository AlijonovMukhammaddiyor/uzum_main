import requests

from uzum.jobs.constants import SELLER_HEADERS, SELLER_URL
from uzum.jobs.helpers import generateUUID, get_random_user_agent


def fetch_shop_api(link: str):
    try:
        response = requests.get(
            SELLER_URL + link + "?categoryId=1",
            headers={
                **SELLER_HEADERS,
                "User-Agent": get_random_user_agent(),
                "x-iid": generateUUID(),
            },
        )
        if response.status_code == 200:
            data: dict = response.json()
            return data.get("payload")
        else:
            return None

    except Exception as e:
        print("Error in fetchShopApi: ", e)
        return None
