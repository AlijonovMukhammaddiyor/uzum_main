import asyncio
import logging
import math
import time
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
import traceback
from requests.adapters import HTTPAdapter

import requests

from uzum.banner.models import Banner
from uzum.jobs.constants import (
    CATEGORIES_HEADER,
    MAIN_PAGE_PAYLOAD,
    MAIN_PAGE_URL,
    MAX_OFFSET,
    PAGE_SIZE,
    PRODUCTIDS_CONCURRENT_REQUESTS,
    PRODUCTS_URL,
)
from uzum.jobs.helpers import generateUUID, get_random_user_agent

# Set up a basic configuration for logging
logging.basicConfig(level=logging.INFO)

# Optionally, disable logging for specific libraries
logging.getLogger("requests").setLevel(logging.ERROR)


def campaign_products_payload(offset: int, limit: int, offerCategoryId: str) -> dict:
    return {
        "operationName": "getMakeSearch",
        "query": "query getMakeSearch( $queryInput: MakeSearchQueryInput!) {makeSearch(query: $queryInput) {items { catalogCard { productId }  } total } }",
        "variables": {
            "queryInput": {
                "categoryId": "1",
                "filters": [],
                "pagination": {"offset": offset, "limit": limit},
                "offerCategoryId": offerCategoryId,
                "showAdultContent": "TRUE",
                "sort": "BY_RELEVANCE_DESC",
            }
        },
    }


def get_main_page_data():
    try:
        response = requests.post(url=MAIN_PAGE_URL, json=MAIN_PAGE_PAYLOAD, headers=CATEGORIES_HEADER)

        if response.status_code == 200:
            return response.json()["data"]["main"]["content"]

    except Exception as e:
        print(f"Error in get_main_page_data: {e}")
        return None


def prepare_banners_data(banners_api):
    try:
        banners = []

        for banner in banners_api:
            if "category/" in banner.get("link"):
                pass

            banners.append(
                {
                    "typename": banner.get("__typename"),
                    "description": banner.get("description"),
                    "link": banner.get("link"),
                    "image": banner.get("image", {"high": None})["high"],
                }
            )

        return banners

    except Exception as e:
        print(f"Error in prepare_banners_data: {e}")
        return None


def get_campaign_products_ids(offer_category_id: int, title: str, retry: bool = False):
    try:
        # has to make parallel requests to get all products
        session = requests.Session()
        response = make_request_campaign_product_ids(
            campaign_products_payload(0, 20, offer_category_id), session=session
        )

        if response.status_code == 200:
            # time.sleep(3)
            if "errors" in response.json() or "error" in response.json():
                print(f"Error in get_campaign_products_ids: {response.json()}")
                return
            data = response.json()["data"]["makeSearch"]

            total = data["total"]

            product_ids, failed_ids = concurrent_requests_for_campaign_product_ids(offer_category_id, total)
        else:
            print(f"Error in get_campaign_products_ids: {response.status_code}")
            # give server some time to recover
            time.sleep(2)
            if not retry:
                get_campaign_products_ids(offer_category_id, title, True)
            return []

        return product_ids

    except Exception as e:
        print(f"Error in get_campaign_products_ids: {e}")
        return None


def concurrent_requests_for_campaign_product_ids(offer_category_id: int, total: int):
    try:
        start_time = time.time()
        promises = []
        eligable_total = min(MAX_OFFSET + PAGE_SIZE, total)
        num_req = math.ceil(eligable_total / PAGE_SIZE)

        for i in range(num_req):
            promises.append(
                {
                    "offset": i * PAGE_SIZE,
                    "pageSize": PAGE_SIZE,
                    "offerCategoryId": offer_category_id,
                }
            )

        failed_ids = []
        product_ids = []
        last_length = 0
        index = 0
        max_connections = 50
        session = requests.Session()
        adapter = HTTPAdapter(pool_maxsize=max_connections)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
        while index < num_req:
            if len(product_ids) - last_length > 4000:
                print("Sleeping for 3 seconds")
                time.sleep(3)
                last_length = len(product_ids)

            with ThreadPoolExecutor(max_workers=PRODUCTIDS_CONCURRENT_REQUESTS) as executor:
                futures = {
                    executor.submit(
                        make_request_campaign_product_ids,
                        campaign_products_payload(
                            promise["offset"],
                            promise["pageSize"],
                            promise["offerCategoryId"],
                        ),
                        session=session,
                    ): promise
                    for promise in promises[index : index + PRODUCTIDS_CONCURRENT_REQUESTS]
                }
                for future in as_completed(futures):
                    promise = futures[future]
                    try:
                        res = future.result()
                        res_data = res.json()
                        if "errors" not in res_data:
                            products = res_data["data"]["makeSearch"]["items"]
                            for product in products:
                                product_ids.append(product["catalogCard"]["productId"])
                        else:
                            failed_ids.append(promise["offerCategoryId"])

                    except Exception as e:
                        traceback.print_exc()
                        print(f"Error in concurrentRequestsForIds inner: {e} - {promise}")
                        time.sleep(2)
                        failed_ids.append(promise)

            index += PRODUCTIDS_CONCURRENT_REQUESTS

        print(
            f"Offer category {offer_category_id} took {time.time() - start_time:.2f} seconds - ",
            f"Total number of products: {len(product_ids)}/{eligable_total}",
        )
        return product_ids, failed_ids

    except Exception as e:
        print(f"Error in concurrent_requests_for_campaign_product_ids: {e}")
        return None


def make_request_campaign_product_ids(
    data,
    retries=3,
    backoff_factor=0.3,
    session=None,
):
    for i in range(retries):
        try:
            return session.post(
                PRODUCTS_URL,
                json=data,
                headers={
                    **CATEGORIES_HEADER,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
            )
        except Exception as e:
            if i == retries - 1:  # This is the last retry, raise the exception
                raise e
            print(f"Error in makeRequestProductIds (attemp:{i}): ", e)
            sleep_time = backoff_factor * (2**i)
            time.sleep(sleep_time)


def associate_with_shop_or_product(link: str):
    try:
        # check if link contains product/ or category/
        print("Link: ", link)
        if "/product/" in link:
            print("Product link found")
            product_id = get_product_and_aku_ids(link)
            if product_id:
                return {"product_id": product_id}
        elif "/category/" not in link:
            words = link.split("/")
            if len(words) == 4:
                return {"shop_id": words[-1]}

        return None
    except Exception as e:
        print(f"Error in associate_with_shop_or_product: {e}")
        return None


def get_product_and_aku_ids(url: str):
    try:
        product_id = url.split("/")[-1]
        if "skuid" in product_id:
            product_id = product_id.split("?")[0].split("-")[-1]
        else:
            product_id = product_id.split("-")[-1]
        return product_id

    except Exception as e:
        print(f"Error in get_product_and_aku_ids: {e}")
        return None
