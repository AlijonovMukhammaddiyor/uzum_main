import math
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

from uzum.banner.models import Banner
from uzum.jobs.constants import (
    CATEGORIES_HEADER,
    MAIN_PAGE_PAYLOAD,
    MAIN_PAGE_URL,
    MAX_OFFSET,
    PAGE_SIZE,
    PRODUCTIDS_CONCURRENT_REQUESTS,
)
from uzum.jobs.product.utils import make_request_product_ids


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
                Banner(
                    **{
                        "typename": banner.get("__typename"),
                        "description": banner.get("description"),
                        "link": banner.get("link"),
                        "image": banner.get("image", {"high": None})["high"],
                    }
                )
            )

    except Exception as e:
        print(f"Error in prepare_banners_data: {e}")
        return None


def create_banners(banners_api):
    try:
        banners = prepare_banners_data(banners_api)
        result = Banner.objects.bulk_create(banners, ignore_conflicts=True)

        return result
    except Exception as e:
        print(f"Error in create_banners: {e}")
        return None


def get_campaign_products_ids(offer_category_id: int, title: str):
    try:
        # has to make parallel requests to get all products
        response = make_request_product_ids(campaign_products_payload(0, 20, offer_category_id))

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
            return None

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
        while index < num_req:
            if len(product_ids) - last_length > 4000:
                print("Sleeping for 3 seconds")
                time.sleep(3)
                last_length = len(product_ids)

            with ThreadPoolExecutor(max_workers=PRODUCTIDS_CONCURRENT_REQUESTS) as executor:
                futures = {
                    executor.submit(
                        make_request_product_ids,
                        campaign_products_payload(
                            promise["offset"],
                            promise["pageSize"],
                            promise["offerCategoryId"],
                        ),
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
                        print(f"Error in concurrentRequestsForIds inner: {e} - {promise}")
                        failed_ids.append(promise)

            index += PRODUCTIDS_CONCURRENT_REQUESTS

        print(
            f"Offer category {offer_category_id} took {time.time() - start_time} seconds - ",
            f"Total number of products: {len(product_ids)}/{eligable_total}",
        )
        return product_ids, failed_ids

    except Exception as e:
        print(f"Error in concurrent_requests_for_campaign_product_ids: {e}")
        return None
