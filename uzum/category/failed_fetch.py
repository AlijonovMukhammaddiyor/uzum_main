import asyncio
import threading
import time
import traceback

import httpx
import requests
from asgiref.sync import async_to_sync
from django.db import transaction

from uzum.category.models import CategoryAnalytics
from uzum.jobs.category.MultiEntry import \
    get_categories_with_less_than_n_products2
from uzum.jobs.constants import (CATEGORIES_HEADER, CATEGORIES_HEADER_RU,
                                 MAX_ID_COUNT, PAGE_SIZE,
                                 POPULAR_SEARCHES_PAYLOAD, PRODUCT_HEADER)
from uzum.jobs.helpers import generateUUID, get_random_user_agent
from uzum.jobs.product.fetch_details import (
    concurrent_requests_product_details, get_product_details_via_ids)
from uzum.jobs.product.fetch_ids import get_all_product_ids_from_uzum
from uzum.jobs.product.MultiEntry import create_products_from_api
from uzum.product.models import ProductAnalytics
from uzum.shop.models import ShopAnalytics
from uzum.utils.general import get_today_pretty


async def make_request(client=None, isRu=False):
    try:
        if isRu:
            return await client.post(
                "https://graphql.uzum.uz/",
                json=POPULAR_SEARCHES_PAYLOAD,
                headers={
                    **CATEGORIES_HEADER_RU,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
            )
        return await client.post(
            "https://graphql.uzum.uz/",
            json=POPULAR_SEARCHES_PAYLOAD,
            headers={
                **CATEGORIES_HEADER,
                "User-Agent": get_random_user_agent(),
                "x-iid": generateUUID(),
            },
        )
    except Exception as e:
        traceback.print_exc()
        print(f"Error in make_request {isRu}:", e)


async def fetch_popular_seaches_from_uzum(words: list[str], isRu=False):
    try:
        async with httpx.AsyncClient() as client:
            tasks = [
                make_request(
                    client=client,
                    isRu=isRu,
                )
                for _ in range(200)
            ]

            results = await asyncio.gather(*tasks, return_exceptions=True)

            for res in results:
                if isinstance(res, Exception):
                    print("Error in fetch_popular_seaches_from_uzum:", res)
                else:
                    if not res:
                        continue
                    if res.status_code != 200:
                        continue
                    res_data = res.json()
                    if "errors" not in res_data:
                        words_ = res_data["data"]["getSuggestions"]["blocks"][0]["popularSuggestions"]
                        words.extend(words_)

    except Exception as e:
        traceback.print_exc()
        return None


def fetch_failed_products(product_ids: list[int]):
    products_api: list[dict] = []
    print("Starting fetching failed products...")
    print("After shop_analytics_done...")
    async_to_sync(get_product_details_via_ids)(product_ids, products_api)
    create_products_from_api(products_api, {})
    del products_api

def fetch_product_ids(date_pretty: str = get_today_pretty()):
    # create_and_update_categories()

    categories_filtered = get_categories_with_less_than_n_products2(MAX_ID_COUNT)
    product_ids: list[int] = []
    async_to_sync(get_all_product_ids_from_uzum)(categories_filtered, product_ids, page_size=PAGE_SIZE)
    product_ids = set(int(id) for id in product_ids)

    existing_product_ids = set(
        ProductAnalytics.objects.filter(date_pretty=date_pretty).values_list("product__product_id", flat=True)
    )
    existing_product_ids = set(int(id) for id in existing_product_ids)

    print(f"Existing products: {len(existing_product_ids)}")

    unfetched_product_ids = list(product_ids - existing_product_ids)
    print(f"Unfetched products: {len(unfetched_product_ids)}")
    unfetched_product_ids = unfetched_product_ids[:25_000]
    shop_analytics_done = {}

    BATCH_SIZE = 10_000

    category_sales_map = {
        analytics.category.categoryId: {
            "products_with_sales": set(),
            "shops_with_sales": set(),
        }
        for analytics in CategoryAnalytics.objects.filter(date_pretty=date_pretty).prefetch_related("category")
    }

    for i in range(0, len(unfetched_product_ids), BATCH_SIZE):
        products_api: list[dict] = []
        print(
            f"Processing batch {i // BATCH_SIZE + 1}/{(len(unfetched_product_ids) + BATCH_SIZE - 1) // BATCH_SIZE}..."
        )
        async_to_sync(get_product_details_via_ids)(unfetched_product_ids[i : i + BATCH_SIZE], products_api)

        # Wrap database interaction in a transaction
        with transaction.atomic():
            create_products_from_api(products_api, {}, shop_analytics_done, category_sales_map)

        time.sleep(30)
        del products_api

def fetch_single_product(product_id):
    try:
        res = requests.get(
            f"https://api.uzum.uz/api/product/{product_id}",
            headers={
                **PRODUCT_HEADER,
                "User-Agent": get_random_user_agent(),
                "x-iid": generateUUID(),
            },
            timeout=60
        )
        if res.status_code != 200:  # Assuming 200 is the successful status code
            print(f"Failed to fetch product {product_id}. Status Code: {res.status_code}")
            return None

        return res.json()
    except Exception as e:
        print("Error in fetch_single_product: ", e)
        return None

NUM_WORKER_THREADS = 10


def fetch_multiple_products(product_ids):
    MAX_RETRIES = 10  # Maximum number of times to retry fetching failed products

    start_total = time.time()
    results = []
    failed = product_ids  # Initially, all product IDs are considered "failed" until successfully fetched.

    for attempt in range(MAX_RETRIES):
        if not failed:
            break  # Exit the loop if there are no more failed products to fetch

        print(f"Attempt {attempt + 1} of {MAX_RETRIES}")
        new_failed = []
        start = time.time()

        async_to_sync(concurrent_requests_product_details)(failed, new_failed, 0, results)

        end = time.time()
        print(f"Failed to fetch {len(new_failed)} products on attempt {attempt + 1}")
        print(f"Time taken for current attempt: {end - start} seconds")

        failed = new_failed  # Update the list of failed products for the next iteration

    print(f"Total results: {len(results)}")
    end_total = time.time()
    print(f"Total time taken: {end_total - start_total} seconds. fetch_multiple_products")

    # return results  # Optionally return the results for further processing

# Multi-threaded processing
def fetch_products_with_threads(product_ids):
    results = []
    failed = []
    start_time = time.time()

    # Adjust the number of worker threads based on your system and requirements
    NUM_WORKER_THREADS = 10
    threads = []

    def worker(subset_ids):
        async_to_sync(concurrent_requests_product_details)(subset_ids, failed, 0, results)

    step_size = len(product_ids) // NUM_WORKER_THREADS

    for i in range(0, len(product_ids), step_size):
        subset_ids = product_ids[i:i + step_size]
        thread = threading.Thread(target=worker, args=(subset_ids,))
        thread.start()
        threads.append(thread)

    for thread in threads:
        thread.join()

    end_time = time.time()
    print(f"Multi-threaded: Time taken: {end_time - start_time} seconds, Failed: {len(failed)}")

MAX_WORKERS = 60
BATCH_SIZE = 60  # Adjust based on the server's rate limit policy
SLEEP_INTERVAL = 1  # In seconds, adjust based on the server's rate limit policy
