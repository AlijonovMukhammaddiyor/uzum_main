import asyncio
import json
import time
import traceback
from collections import Counter
from datetime import datetime

import httpx
import pytz
from asgiref.sync import async_to_sync
from django.core.cache import cache

from config import celery_app
from uzum.banner.models import Banner
from uzum.category.models import Category, CategoryAnalytics
from uzum.jobs.campaign.main import update_or_create_campaigns
from uzum.jobs.campaign.utils import associate_with_shop_or_product, get_product_and_aku_ids
from uzum.jobs.category.main import create_and_update_categories
from uzum.jobs.category.MultiEntry import get_categories_with_less_than_n_products
from uzum.jobs.constants import CATEGORIES_HEADER, MAX_OFFSET, PAGE_SIZE, POPULAR_SEARCHES_PAYLOAD
from uzum.jobs.helpers import generateUUID, get_random_user_agent
from uzum.jobs.product.fetch_details import get_product_details_via_ids
from uzum.jobs.product.fetch_ids import get_all_product_ids_from_uzum
from uzum.jobs.product.MultiEntry import create_products_from_api
from uzum.product.models import Product, ProductAnalytics, get_today_pretty
from uzum.product.views import PopularWords
from uzum.review.models import PopularSeaches
from uzum.shop.models import Shop, ShopAnalytics


@celery_app.task(
    name="update_uzum_data",
)
def update_uzum_data(args=None, **kwargs):
    print(get_today_pretty())
    print(datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%H:%M:%S" + " - " + "%d/%m/%Y"))

    create_and_update_categories()
    # await create_and_update_products()

    # 1. Get all categories which have less than N products
    categories_filtered = get_categories_with_less_than_n_products(MAX_OFFSET + PAGE_SIZE)
    product_ids: list[int] = []
    async_to_sync(get_all_product_ids_from_uzum)(
        categories_filtered,
        product_ids,
        page_size=PAGE_SIZE,
    )

    product_ids = list(set(product_ids))

    product_campaigns, product_associations, shop_association = update_or_create_campaigns()

    shop_analytics_done = {}

    BATCH_SIZE = 10_000

    for i in range(0, len(product_ids), BATCH_SIZE):
        products_api: list[dict] = []
        print(f"{i}/{len(product_ids)}")
        async_to_sync(get_product_details_via_ids)(product_ids[i : i + BATCH_SIZE], products_api)
        create_products_from_api(products_api, product_campaigns, shop_analytics_done)
        time.sleep(30)
        del products_api

    time.sleep(600)

    fetch_product_ids(product_ids)

    time.sleep(30)

    print("Setting banners...", product_associations, shop_association)
    print(product_associations, shop_association)
    for product_id, banners in product_associations.items():
        try:
            product = Product.objects.get(product_id=product_id)
            product_analytics = ProductAnalytics.objects.get(product=product, date_pretty=get_today_pretty())

            product_analytics.banners.set(banners)
            product_analytics.save()

            print(f"Product {product.title} banners set")
        except Exception as e:
            print("Error in setting banner(s): ", e)

    for link, banners in shop_association.items():
        try:
            shop_an = ShopAnalytics.objects.filter(shop=Shop.objects.get(link=link), date_pretty=get_today_pretty())

            if len(shop_an) == 0:
                continue
            target = shop_an.order_by("-created_at").first()  # get most recently created analytics
            target.banners.set(banners)
            target.save()

            print(f"Shop {link} banner(s) set")
        except Exception as e:
            print("Error in setting shop banner(s): ", e)

    date_pretty = get_today_pretty()

    create_todays_searches()

    Category.update_descendants()

    shop_analytics = ShopAnalytics.objects.filter(date_pretty=date_pretty)

    for shop_an in shop_analytics:
        shop_an.set_total_products()

    # asyncio.create_task(create_and_update_products())
    print("Uzum data updated...")
    return True


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


def fetch_product_ids(product_ids, date_pretty: str = get_today_pretty()):
    # create_and_update_categories()

    categories_filtered = get_categories_with_less_than_n_products(MAX_OFFSET + PAGE_SIZE)
    # product_ids: list[int] = []
    # async_to_sync(get_all_product_ids_from_uzum)(
    #     categories_filtered,
    #     product_ids,
    #     page_size=PAGE_SIZE,
    # )
    product_ids = set(product_ids)

    aa = ProductAnalytics.objects.filter(date_pretty=date_pretty).values_list("product__product_id", flat=True)

    unfetched_product_ids = list(product_ids - set(aa))
    # remove already fetched products from product_ids
    # for product_id in product_ids:
    #     if product_id not in aa:
    #         unfetched_product_ids.append(product_id)

    shop_analytics_done = {}

    BATCH_SIZE = 10_000

    for i in range(0, len(unfetched_product_ids), BATCH_SIZE):
        products_api: list[dict] = []
        print(f"{i}/{len(unfetched_product_ids)}")
        async_to_sync(get_product_details_via_ids)(unfetched_product_ids[i : i + BATCH_SIZE], products_api)
        create_products_from_api(products_api, {}, shop_analytics_done)
        time.sleep(30)
        del products_api


def set_banners_for_product_analytics(date_pretty=get_today_pretty()):
    try:
        today_date_in_uz = datetime.now(tz=pytz.timezone("Asia/Tashkent")).date()
        banners_today = Banner.objects.filter(created_at__date=today_date_in_uz)

        for banner in banners_today:
            assoc = associate_with_shop_or_product(banner.link)

            if assoc is None:
                continue

            if "product_id" in assoc:
                analytics_today = ProductAnalytics.objects.filter(
                    product__product_id=assoc["product_id"], date_pretty=date_pretty
                )
                if len(analytics_today) == 0:
                    continue

                if len(analytics_today) > 1:
                    print("More than one analytics for product", assoc["product_id"], len(analytics_today))

                analytics_today = analytics_today.first()
                analytics_today.banners.add(banner)
                analytics_today.save()

            elif "shop_id" in assoc:
                shop_an = ShopAnalytics.objects.filter(
                    shop=Shop.objects.get(link=assoc["shop_id"]), date_pretty=date_pretty
                )

                if len(shop_an) == 0:
                    continue

                if len(shop_an) > 1:
                    print("More than one analytics for shop", assoc["shop_id"], len(shop_an))
                target = shop_an.order_by("-created_at").first()  # get most recently created analytics
                target.banners.add(banner)
                target.save()

    except Exception as e:
        print("Error in setting banner(s): ", e)


async def make_request(client=None):
    try:
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
        print("Error in makeRequestProductIds: ", e)


async def fetch_popular_seaches_from_uzum(words: list[str]):
    try:
        async with httpx.AsyncClient() as client:
            tasks = [
                make_request(
                    client=client,
                )
                for _ in range(100)
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


def create_todays_searches():
    try:
        words = []
        async_to_sync(fetch_popular_seaches_from_uzum)(words)
        word_count = Counter(words)
        if not word_count:
            return None
        if len(word_count) == 0:
            return None

        obj = PopularSeaches.objects.filter(date_pretty=get_today_pretty())

        if obj.exists():
            return None

        PopularSeaches.objects.create(
            words=json.dumps(word_count),
            requests_count=100,
            date_pretty=get_today_pretty(),
        )
    except Exception as e:
        print("Error in create_todays_searches:", e)
        return None


def update_category_tree():
    categories = Category.objects.values("categoryId", "title", "parent_id")

    # first create a dictionary mapping ids to category data
    category_dict = {category["categoryId"]: category for category in categories}

    # then build a mapping from parent_id to a list of its children
    children_map = {}
    for category in categories:
        children_map.setdefault(category["parent_id"], []).append(category)

    # recursive function to build the tree
    def build_tree(category_id):
        category = category_dict[category_id]
        children = children_map.get(category_id, [])
        return {
            "categoryId": category_id,
            "title": category["title"],
            "children": [build_tree(child["categoryId"]) for child in children],
        }

    # build the tree starting from the root
    category_tree = build_tree(1)
    # store in cache
    cache.set("category_tree", category_tree, timeout=60 * 60 * 48)  # 48 hours
    return category_tree
