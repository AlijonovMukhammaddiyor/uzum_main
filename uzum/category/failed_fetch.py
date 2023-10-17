import asyncio
import time
import traceback

import httpx
from asgiref.sync import async_to_sync
from django.db import transaction

from uzum.category.models import CategoryAnalytics
from uzum.jobs.category.MultiEntry import \
    get_categories_with_less_than_n_products2
from uzum.jobs.constants import (CATEGORIES_HEADER, CATEGORIES_HEADER_RU,
                                 MAX_ID_COUNT, PAGE_SIZE,
                                 POPULAR_SEARCHES_PAYLOAD)
from uzum.jobs.helpers import generateUUID, get_random_user_agent
from uzum.jobs.product.fetch_details import get_product_details_via_ids
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
    shop_analytics_done = {
        seller_id: True
        for seller_id in ShopAnalytics.objects.filter(date_pretty=get_today_pretty()).values_list(
            "shop__seller_id", flat=True
        )
    }
    print("After shop_analytics_done...")
    async_to_sync(get_product_details_via_ids)(product_ids, products_api)
    create_products_from_api(products_api, {}, shop_analytics_done)
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
