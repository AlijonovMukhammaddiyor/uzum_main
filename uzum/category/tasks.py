import asyncio
import json
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta
from itertools import chain

import httpx
import pytz
from asgiref.sync import async_to_sync
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Case, Value, When, Max
from django.utils import timezone
from config import celery_app
from uzum.banner.models import Banner
from uzum.category.models import Category, CategoryAnalytics
from uzum.jobs.campaign.main import update_or_create_campaigns
from uzum.jobs.campaign.utils import associate_with_shop_or_product
from uzum.jobs.category.main import create_and_update_categories
from uzum.jobs.category.MultiEntry import (
    get_categories_with_less_than_n_products,
    get_categories_with_less_than_n_products2,
    get_categories_with_less_than_n_products_for_russian_title,
)
from uzum.jobs.category.utils import add_russian_titles, get_categories_tree
from uzum.jobs.constants import (
    CATEGORIES_HEADER,
    CATEGORIES_HEADER_RU,
    MAX_ID_COUNT,
    PAGE_SIZE,
    POPULAR_SEARCHES_PAYLOAD,
)
from uzum.jobs.helpers import generateUUID, get_random_user_agent
from uzum.jobs.product.fetch_details import get_product_details_via_ids
from uzum.jobs.product.fetch_ids import get_all_product_ids_from_uzum
from uzum.jobs.product.MultiEntry import create_products_from_api
from uzum.product.models import Product, ProductAnalytics, create_product_latestanalytics
from uzum.review.models import PopularSeaches
from uzum.shop.models import Shop, ShopAnalytics
from uzum.sku.models import SkuAnalytics
from uzum.users.tasks import send_reports_to_all
from uzum.utils.general import get_day_before_pretty, get_today_pretty


@celery_app.task(
    name="update_uzum_data",
)
def update_uzum_data(args=None, **kwargs):
    print(get_today_pretty())
    date_pretty = get_today_pretty()
    print(datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%H:%M:%S" + " - " + "%d/%m/%Y"))
    print("Updating category parents")
    start = time.time()
    update_all_category_parents()
    Category.update_descendants()
    print("Time taken: ", time.time() - start)
    create_and_update_categories()
    # await create_and_update_products()
    root = CategoryAnalytics.objects.filter(category__categoryId=1, date_pretty=get_today_pretty())
    print("total_products: ", root[0].total_products)
    # 1. Get all categories which have less than N products
    categories_filtered = get_categories_with_less_than_n_products(MAX_ID_COUNT)

    product_ids: list[int] = []
    async_to_sync(get_all_product_ids_from_uzum)(
        categories_filtered,
        product_ids,
        page_size=PAGE_SIZE,
    )

    print(f"Total product ids: {len(product_ids)}")

    product_ids = list(set(product_ids))

    product_campaigns, product_associations, shop_association = update_or_create_campaigns()

    shop_analytics_done = {}

    BATCH_SIZE = 10_000

    print("Creatig create_product_latestanalytics")
    start = time.time()
    create_product_latestanalytics(get_day_before_pretty(date_pretty))

    # create {category_id: { products_with_sales: set(), shops_with_sales: set()}} for each category
    category_sales_map = {
        analytics.category.categoryId: {
            "products_with_sales": set(),
            "shops_with_sales": set(),
        }
        for analytics in CategoryAnalytics.objects.filter(date_pretty=date_pretty).prefetch_related("category")
    }

    vacuum_table("category_categoryanalytics")
    vacuum_table("product_productanalytics")
    vacuum_table("shop_shopanalytics")
    vacuum_table("sku_skuanalytics")

    for i in range(0, len(product_ids), BATCH_SIZE):
        products_api: list[dict] = []
        print(f"{i}/{len(product_ids)}")
        async_to_sync(get_product_details_via_ids)(product_ids[i : i + BATCH_SIZE], products_api)
        create_products_from_api(products_api, product_campaigns, shop_analytics_done, category_sales_map)
        time.sleep(10)
        del products_api
    Category.update_descendants()

    time.sleep(10)

    # add_russian_titles()

    print("Setting banners...", product_associations, shop_association)
    print(product_associations, shop_association)
    bulk_remove_duplicate_product_analytics(date_pretty)

    # for product_id, banners in product_associations.items():
    #     try:
    #         product = Product.objects.get(product_id=product_id)
    #         product_analytics = ProductAnalytics.objects.filter(product=product, date_pretty=get_today_pretty())

    #         if len(product_analytics) > 0:
    #             # get the most recently created analytics
    #             product_analytics = product_analytics.order_by("-created_at").first()

    #         product_analytics.banners.set(banners)
    #         product_analytics.save()

    #         print(f"Product {product.title} banners set")
    #     except Exception as e:
    #         print("Error in setting banner(s): ", e)

    # for link, banners in shop_association.items():
    #     try:
    #         shop_an = ShopAnalytics.objects.filter(shop=Shop.objects.get(link=link), date_pretty=get_today_pretty())

    #         if len(shop_an) > 0:
    #             shop_an = shop_an.order_by("-created_at").first()

    #         if len(shop_an) == 0:
    #             continue
    #         target = shop_an.order_by("-created_at").first()  # get most recently created analytics
    #         target.banners.set(banners)
    #         target.save()

    #         print(f"Shop {link} banner(s) set")
    #     except Exception as e:
    #         print("Error in setting shop banner(s): ", e)

    create_todays_searches()

    bulk_remove_duplicate_category_analytics(date_pretty)
    bulk_remove_duplicate_product_analytics(date_pretty)
    bulk_remove_duplicate_shop_analytics(date_pretty)
    bulk_remove_duplicate_sku_analytics(date_pretty)

    vacuum_table("category_categoryanalytics")
    update_category_with_sales(category_sales_map, date_pretty)

    # print("Updating Category Descendants...")
    # start = time.time()
    # Category.update_descendants()
    # print(f"Category Descendants updated in {time.time() - start} seconds")
    time.sleep(60)
    print("Updating Analytics...")
    start = time.time()
    vacuum_table("category_categoryanalytics")
    update_analytics(date_pretty)
    print(f"Analytics updated in {time.time() - start} seconds")

    print("Uzum data updated...")
    print("Sendinf reports")
    start = time.time()
    send_reports_to_all()
    print(f"Reports sent in {time.time() - start} seconds")
    update_monthly_for_shops(date_pretty)
    update_category_tree_with_monthly_data(date_pretty)
    update_category_tree_with_weekly_data(date_pretty)
    return True


def update_category_with_sales(category_sales_map, date_pretty=get_today_pretty()):
    try:
        start = time.time()

        # Fetch all the relevant CategoryAnalytics objects at once
        category_ids = list(category_sales_map.keys())
        categories = CategoryAnalytics.objects.filter(category__categoryId__in=category_ids, date_pretty=date_pretty)

        # Store the CategoryAnalytics objects in a dictionary for quick access
        category_dict = {cat.category.categoryId: cat for cat in categories}

        to_update = []  # List to store the updated CategoryAnalytics objects

        for category_id, sales in category_sales_map.items():
            category = category_dict.get(category_id)
            if not category:
                continue

            descendants = [category_id]
            if category.category.descendants:
                descendants.extend(map(int, category.category.descendants.split(",")))
                descendants = list(set(descendants))

            # update total_products_with_sales
            # category.total_products_with_sales = sum(
            #     len(category_sales_map.get(c_id, {}).get("products_with_sales", [])) for c_id in descendants
            # )
            # first get all product ids in set to remove duplicates
            product_ids = set()
            for c_id in descendants:
                product_ids.update(category_sales_map.get(c_id, {}).get("products_with_sales", []))

            category.total_products_with_sales = len(product_ids)

            # update total_shops_with_sales
            # category.total_shops_with_sales = sum(
            #     len(category_sales_map.get(c_id, {}).get("shops_with_sales", [])) for c_id in descendants
            # )
            # first get all shop ids in set to remove duplicates
            shop_ids = set()
            for c_id in descendants:
                shop_ids.update(category_sales_map.get(c_id, {}).get("shops_with_sales", []))
            category.total_shops_with_sales = len(shop_ids)

            to_update.append(category)

        # Update the CategoryAnalytics objects in bulk
        CategoryAnalytics.objects.bulk_update(to_update, ["total_products_with_sales", "total_shops_with_sales"])

        print(f"Category with sales updated in {time.time() - start} seconds")
    except Exception as e:
        print("Error in update_category_with_sales: ", e)
        traceback.print_exc()
        return None


def update_all_category_parents():
    try:
        tree = get_categories_tree()
        cat_parents = {}  # mapping from id to parent id
        all_categories = {}
        Category.objects.all().update(parent=None)

        for i, category in enumerate(tree):
            if category["category"]["id"] != 1:
                cat_parents[category["category"]["id"]] = category["category"]["parent"]["id"]

        categories_qs = Category.objects.filter(categoryId__in=cat_parents.keys())
        parent_qs = Category.objects.filter(categoryId__in=cat_parents.values())

        # Build dictionary for quick access
        for category in chain(categories_qs, parent_qs):
            all_categories[category.categoryId] = category

        # Update parent of each category
        for cat_id, parent_id in cat_parents.items():
            cat = all_categories[cat_id]
            parent = all_categories[parent_id]
            cat.parent = parent
            cat.save()
            # print(f"Category {cat.title} parent set to {parent.title}")
    except Exception as e:
        print("Error in update_all_category_parents:", e)
        traceback.print_exc()


def update_analytics(date_pretty: str):
    try:
        yesterday_pretty = get_day_before_pretty(date_pretty)
        create_product_latestanalytics(yesterday_pretty)
        start = time.time()
        vacuum_table("product_productanalytics")
        ProductAnalytics.update_analytics(date_pretty)
        print(f"ProductAnalytics updated in {time.time() - start} seconds")
        start = time.time()
        ShopAnalytics.update_analytics(date_pretty)
        print(f"ShopAnalytics updated in {time.time() - start} seconds")
        start = time.time()
        CategoryAnalytics.update_analytics(date_pretty)
        print(f"CategoryAnalytics updated in {time.time() - start} seconds")

        print(f"Creating latest analytics for {date_pretty}...")
        create_product_latestanalytics(date_pretty=date_pretty)
        insert_shop_analytics(date_pretty=date_pretty)

        print("Updating category tree...")
        update_category_tree()

        update_category_tree_with_data()

        print("Creating Materialized View...")
        start = time.time()
        create_materialized_view(date_pretty)
        print(f"Materialized View created in {time.time() - start} seconds")
        print("Setting banners...")
        Banner.set_products()

    except Exception as e:
        print("Error in update_analytics:", e)
        traceback.print_exc()


def add_product_russian_titles():
    try:
        tree = get_categories_tree()
        cat_totals = {}  # mapping from id to total products given in api response

        for i, category in enumerate(tree):
            cat_totals[category["category"]["id"]] = category["total"]

        print("MAX_ID_COUNT: ", MAX_ID_COUNT)
        categories_filtered = get_categories_with_less_than_n_products_for_russian_title(MAX_ID_COUNT, cat_totals)
        product_ids: list[dict] = []  # it is [{productId: int, title: str}]

        async_to_sync(get_all_product_ids_from_uzum)(
            categories_filtered,
            product_ids,
            page_size=PAGE_SIZE,
            is_ru=True,
        )

        # find which products has no russian title
        ids = Product.objects.filter(title_ru__isnull=True).values_list("product_id", flat=True)

        # remove duplicate product ids
        product_ids_dict = {d["productId"]: d["title"] for d in product_ids if d["productId"] in ids}
        product_ids = [{"productId": k, "title": v} for k, v in product_ids_dict.items()]
        print(f"Total product ids: {len(product_ids)}")

        with transaction.atomic():
            with connection.cursor() as cursor:
                # Create mapping table
                cursor.execute(
                    """
                    DROP TABLE IF EXISTS product_id_title_mapping;
                    CREATE TABLE product_id_title_mapping (
                        product_id INT PRIMARY KEY,
                        new_title TEXT
                    );
                """
                )

                # Insert product id and new title mapping into the table using batch insert
                values = ", ".join(["(%s, %s)"] * len(product_ids))
                query = f"""
                    INSERT INTO product_id_title_mapping (product_id, new_title)
                    VALUES {values}
                """
                cursor.execute(query, sum([list(item.values()) for item in product_ids], []))

                # Update product titles based on the mapping table only if title_ru is null
                cursor.execute(
                    """
                    UPDATE product_product
                    SET title_ru = product_id_title_mapping.new_title
                    FROM product_id_title_mapping
                    WHERE product_product.product_id = product_id_title_mapping.product_id
                    """
                )

    except Exception as e:
        print("Error in add_russian_titles: ", e)
        traceback.print_exc()
        return None


def add_product_russian_characteristics():
    try:
        tree = get_categories_tree()
        cat_totals = {}  # mapping from id to total products given in api response

        for i, category in enumerate(tree):
            cat_totals[category["category"]["id"]] = category["total"]

        print("MAX_ID_COUNT: ", MAX_ID_COUNT)
        categories_filtered = get_categories_with_less_than_n_products_for_russian_title(MAX_ID_COUNT, cat_totals)
        product_ids: list[dict] = []  # it is [{productId: int, title: str}]

        async_to_sync(get_all_product_ids_from_uzum)(
            categories_filtered,
            product_ids,
            page_size=PAGE_SIZE,
            is_ru=True,
        )

        # find which products has no russian title
        ids = Product.objects.filter(title_ru__isnull=True).values_list("product_id", flat=True)

        # remove duplicate product ids
        product_ids_dict = {d["productId"]: d["characteristicValues"] for d in product_ids if d["productId"] in ids}
        product_ids = [{"productId": k, "characteristics": v} for k, v in product_ids_dict.items()]
        print(f"Total product ids: {len(product_ids)}")

        with transaction.atomic():
            with connection.cursor() as cursor:
                # Create mapping table
                cursor.execute(
                    """
                    DROP TABLE IF EXISTS product_id_charcateristics_mapping;
                    CREATE TABLE product_id_charcateristics_mapping (
                        product_id INT PRIMARY KEY,
                        characteristics TEXT
                    );
                """
                )

                # Insert product id and new title mapping into the table using batch insert
                values = ", ".join(["(%s, %s)"] * len(product_ids))
                query = f"""
                    INSERT INTO product_id_charcateristics_mapping (product_id, characteristics)
                    VALUES {values}
                """
                cursor.execute(query, sum([list(item.values()) for item in product_ids], []))

                # Update product titles based on the mapping table only if title_ru is null
                cursor.execute(
                    """
                    UPDATE product_product
                    SET characteristics_ru = product_id_charcateristics_mapping.characteristics
                    FROM product_id_charcateristics_mapping
                    WHERE product_product.product_id = product_id_charcateristics_mapping.product_id
                    """
                )

    except Exception as e:
        print("Error in add_russian_titles: ", e)
        traceback.print_exc()
        return None


def insert_shop_analytics(date_pretty):
    date = (
        pytz.timezone("Asia/Tashkent")
        .localize(datetime.strptime(date_pretty, "%Y-%m-%d"))
        .replace(hour=23, minute=59, second=59, microsecond=999999)
    )

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO shop_analytics (date_pretty, total_revenue, total_reviews, total_orders)
            SELECT
                '{date_pretty}' AS date_pretty,
                SUM(total_revenue) as total_revenue,
                SUM(total_reviews) as total_reviews,
                SUM(total_orders) as total_orders
            FROM (
                SELECT DISTINCT ON (shop_id)
                    shop_id,
                    total_revenue,
                    total_reviews,
                    total_orders
                FROM shop_shopanalytics
                WHERE created_at <= '{date}'
                ORDER BY shop_id, created_at DESC
            ) AS latest_shop_analytics
            """
        )


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


def create_todays_searches():
    try:
        words = []
        async_to_sync(fetch_popular_seaches_from_uzum)(words)
        word_count = Counter(words)
        if not word_count:
            return None
        if len(word_count) == 0:
            return None

        words_ru = []
        async_to_sync(fetch_popular_seaches_from_uzum)(words_ru, isRu=True)
        word_count_ru = Counter(words_ru)
        if not word_count_ru:
            return None
        if len(word_count_ru) == 0:
            return None

        obj = PopularSeaches.objects.filter(date_pretty=get_today_pretty())

        if obj.exists():
            return None

        PopularSeaches.objects.create(
            words=json.dumps(word_count),
            words_ru=json.dumps(word_count_ru),
            requests_count=100,
            date_pretty=get_today_pretty(),
        )
    except Exception as e:
        print("Error in create_todays_searches:", e)
        return None


def update_category_tree(date_pretty=get_today_pretty()):
    categories = Category.objects.filter(categoryanalytics__date_pretty=date_pretty).values(
        "categoryId", "title", "title_ru", "parent_id"
    )

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
            "title_ru": category["title_ru"],
            "children": [build_tree(child["categoryId"]) for child in children],
        }

    # build the tree starting from the root
    category_tree = build_tree(1)
    # store in cache
    cache.set("category_tree", category_tree, timeout=60 * 60 * 48)  # 48 hours
    # return category_tree


def fetch_latest_analytics(date):
    with connection.cursor() as cursor:
        # Create the materialized view
        cursor.execute(
            f"""
            SELECT DISTINCT ON (category_id) category_id,
                total_orders_amount,
                total_orders,
                total_products,
                total_reviews,
                total_shops
            FROM category_categoryanalytics
            WHERE created_at <= '{date}'
            ORDER BY category_id, created_at DESC
        """
        )

        columns = [col[0] for col in cursor.description]

        # Fetch all rows
        rows = cursor.fetchall()

    # Convert query results to list of dictionaries
    analytics_data = [dict(zip(columns, row)) for row in rows]

    return {data["category_id"]: data for data in analytics_data}


def update_category_tree_with_weekly_data(date_pretty=get_today_pretty()):
    if date_pretty is None:
        date_pretty = get_today_pretty()
    try:
        categories = Category.objects.filter(
            categoryanalytics__date_pretty=date_pretty,
        ).values("categoryId", "title", "title_ru", "parent_id")

        # first create a dictionary mapping ids to category data
        category_dict = {category["categoryId"]: category for category in categories}

        # then build a mapping from parent_id to a list of its children
        children_map = {}
        for category in categories:
            children_map.setdefault(category["parent_id"], []).append(category)

        # get analytics data
        analytics_data = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty()).values(
            "category_id",
            "total_orders_amount",
            "total_orders",
            "total_products",
            "total_reviews",
            "total_shops",
        )
        analytics_dict = {data["category_id"]: data for data in analytics_data}

        thirty_days_ago = (datetime.now(tz=pytz.timezone("Asia/Tashkent")) - timedelta(days=7)).replace(
            hour=0, minute=0, second=59, microsecond=0
        )
        monthly_analytics_data = fetch_latest_analytics(thirty_days_ago)

        for data in analytics_dict.values():
            monthly_data = monthly_analytics_data.get(data["category_id"], {})
            if not monthly_data:
                print("No monthly data for category: ", data["category_id"])
            for key in ["total_orders_amount", "total_orders", "total_products", "total_reviews", "total_shops"]:
                data[key] = data.get(key, 0) - monthly_data.get(key, 0)

        min_max_data = CategoryAnalytics.objects.filter(
            date_pretty=get_today_pretty(), category__child_categories=None
        ).values(
            "category_id",
            "total_orders_amount",
            "total_orders",
            "total_products",
            "total_reviews",
            "total_shops",
        )

        min_max_dict = {data["category_id"]: data for data in min_max_data}

        for data in min_max_dict.values():
            monthly_data = monthly_analytics_data.get(data["category_id"], {})
            if not monthly_data:
                print("No monthly data for category: ", data["category_id"])
            for key in ["total_orders_amount", "total_orders", "total_products", "total_reviews", "total_shops"]:
                data[key] = data.get(key, 0) - monthly_data.get(key, 0)

        # get min and max values for each type of analytics
        min_max = {
            "total_orders_amount": {
                "min": max(0, min([data["total_orders_amount"] for data in min_max_dict.values()])),
                "max": max([data["total_orders_amount"] for data in min_max_dict.values()]),
            },
            "total_orders": {
                "min": max(0, min([data["total_orders"] for data in min_max_dict.values()])),
                "max": max([data["total_orders"] for data in min_max_dict.values()]),
            },
            "total_reviews": {
                "min": max(0, min([data["total_reviews"] for data in min_max_dict.values()])),
                "max": max([data["total_reviews"] for data in min_max_dict.values()]),
            },
            "total_shops": {
                "min": max(0, min([data["total_shops"] for data in min_max_dict.values()])),
                "max": max([data["total_shops"] for data in min_max_dict.values()]),
            },
            "total_products": {
                "min": max(0, min([data["total_products"] for data in min_max_dict.values()])),
                "max": max([data["total_products"] for data in min_max_dict.values()]),
            },
        }

        # create a dictionary mapping category_id to analytics data
        # recursive function to build the tree
        def build_tree(category_id, type):
            category = category_dict[category_id]
            analytics = analytics_dict.get(category_id, {})
            children = children_map.get(category_id, [])
            res = {
                "categoryId": category_id,
                "title": category["title"],
                "title_ru": category["title_ru"],
                "analytics": analytics.get(type, 0),
                "children": [build_tree(child["categoryId"], type) for child in children],
            }

            # if children is empty remove it
            if len(res["children"]) == 0:
                del res["children"]
            return res

        category_tree_revenue = build_tree(1, type="total_orders_amount")
        category_tree_orders = build_tree(1, type="total_orders")
        category_tree_reviews = build_tree(1, type="total_reviews")
        category_tree_shops = build_tree(1, type="total_shops")
        category_tree_products = build_tree(1, type="total_products")

        # store in cache
        # cache.set("category_tree_data", category_tree, timeout=60 * 60 * 48)  # 48 hours
        # print("revenue tree: ", category_tree_revenue)

        cache.set(
            "category_tree_weekly_revenue",
            {"data": category_tree_revenue, "min_max": min_max["total_orders_amount"]},
            timeout=60 * 60 * 48,
        )  # 48 hours

        cache.set(
            "category_tree_weekly_orders",
            {"data": category_tree_orders, "min_max": min_max["total_orders"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_weekly_reviews",
            {"data": category_tree_reviews, "min_max": min_max["total_reviews"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_weekly_shops",
            {"data": category_tree_shops, "min_max": min_max["total_shops"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_weekly_products",
            {"data": category_tree_products, "min_max": min_max["total_products"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
    except Exception as e:
        print("Error in update_category_tree_with_weekly_data: ", e)
        traceback.print_exc()
        return None


def update_category_tree_with_monthly_data(date_pretty=None):
    if date_pretty is None:
        date_pretty = get_today_pretty()
    try:
        categories = Category.objects.filter(
            categoryanalytics__date_pretty=date_pretty,
        ).values("categoryId", "title", "title_ru", "parent_id")

        # first create a dictionary mapping ids to category data
        category_dict = {category["categoryId"]: category for category in categories}

        # then build a mapping from parent_id to a list of its children
        children_map = {}
        for category in categories:
            children_map.setdefault(category["parent_id"], []).append(category)

        # get analytics data
        analytics_data = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty()).values(
            "category_id",
            "total_orders_amount",
            "total_orders",
            "total_products",
            "total_reviews",
            "total_shops",
        )
        analytics_dict = {data["category_id"]: data for data in analytics_data}

        thirty_days_ago = (datetime.now(tz=pytz.timezone("Asia/Tashkent")) - timedelta(days=30)).replace(
            hour=0, minute=0, second=59, microsecond=0
        )
        monthly_analytics_data = fetch_latest_analytics(thirty_days_ago)

        for data in analytics_dict.values():
            monthly_data = monthly_analytics_data.get(data["category_id"], {})
            if not monthly_data:
                print("No monthly data for category: ", data["category_id"])
            for key in ["total_orders_amount", "total_orders", "total_products", "total_reviews", "total_shops"]:
                data[key] = data.get(key, 0) - monthly_data.get(key, 0)

        min_max_data = CategoryAnalytics.objects.filter(
            date_pretty=get_today_pretty(), category__child_categories=None
        ).values(
            "category_id",
            "total_orders_amount",
            "total_orders",
            "total_products",
            "total_reviews",
            "total_shops",
        )

        min_max_dict = {data["category_id"]: data for data in min_max_data}

        for data in min_max_dict.values():
            monthly_data = monthly_analytics_data.get(data["category_id"], {})
            if not monthly_data:
                print("No monthly data for category: ", data["category_id"])
            for key in ["total_orders_amount", "total_orders", "total_products", "total_reviews", "total_shops"]:
                data[key] = data.get(key, 0) - monthly_data.get(key, 0)

        # get min and max values for each type of analytics
        min_max = {
            "total_orders_amount": {
                "min": max(0, min([data["total_orders_amount"] for data in min_max_dict.values()])),
                "max": max([data["total_orders_amount"] for data in min_max_dict.values()]),
            },
            "total_orders": {
                "min": max(0, min([data["total_orders"] for data in min_max_dict.values()])),
                "max": max([data["total_orders"] for data in min_max_dict.values()]),
            },
            "total_reviews": {
                "min": max(0, min([data["total_reviews"] for data in min_max_dict.values()])),
                "max": max([data["total_reviews"] for data in min_max_dict.values()]),
            },
            "total_shops": {
                "min": max(0, min([data["total_shops"] for data in min_max_dict.values()])),
                "max": max([data["total_shops"] for data in min_max_dict.values()]),
            },
            "total_products": {
                "min": max(0, min([data["total_products"] for data in min_max_dict.values()])),
                "max": max([data["total_products"] for data in min_max_dict.values()]),
            },
        }

        print(min_max)

        # create a dictionary mapping category_id to analytics data
        # recursive function to build the tree
        def build_tree(category_id, type):
            category = category_dict[category_id]
            analytics = analytics_dict.get(category_id, {})
            children = children_map.get(category_id, [])
            res = {
                "categoryId": category_id,
                "title": category["title"],
                "title_ru": category["title_ru"],
                "analytics": analytics.get(type, 0),
                "children": [build_tree(child["categoryId"], type) for child in children],
            }

            # if children is empty remove it
            if len(res["children"]) == 0:
                del res["children"]
            return res

        category_tree_revenue = build_tree(1, type="total_orders_amount")
        category_tree_orders = build_tree(1, type="total_orders")
        category_tree_reviews = build_tree(1, type="total_reviews")
        category_tree_shops = build_tree(1, type="total_shops")
        category_tree_products = build_tree(1, type="total_products")

        # store in cache
        # cache.set("category_tree_data", category_tree, timeout=60 * 60 * 48)  # 48 hours
        # print("revenue tree: ", category_tree_revenue)

        cache.set(
            "category_tree_monthly_revenue",
            {"data": category_tree_revenue, "min_max": min_max["total_orders_amount"]},
            timeout=60 * 60 * 48,
        )  # 48 hours

        cache.set(
            "category_tree_monthly_orders",
            {"data": category_tree_orders, "min_max": min_max["total_orders"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_monthly_reviews",
            {"data": category_tree_reviews, "min_max": min_max["total_reviews"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_monthly_shops",
            {"data": category_tree_shops, "min_max": min_max["total_shops"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_monthly_products",
            {"data": category_tree_products, "min_max": min_max["total_products"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
    except Exception as e:
        print("Error in update_category_tree_with_monthly_data:", e)
        traceback.print_exc()


def update_category_tree_with_data(date_pretty=get_today_pretty()):
    categories = Category.objects.filter(
        categoryanalytics__date_pretty=date_pretty,
    ).values("categoryId", "title", "title_ru", "parent_id")

    # first create a dictionary mapping ids to category data
    category_dict = {category["categoryId"]: category for category in categories}

    # then build a mapping from parent_id to a list of its children
    children_map = {}
    for category in categories:
        children_map.setdefault(category["parent_id"], []).append(category)

    # get analytics data
    analytics_data = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty()).values(
        "category_id",
        "total_orders_amount",
        "total_orders",
        "total_products",
        "total_reviews",
        "total_shops",
    )

    min_max_data = CategoryAnalytics.objects.filter(
        date_pretty=get_today_pretty(), category__child_categories=None
    ).values(
        "category_id",
        "total_orders_amount",
        "total_orders",
        "total_products",
        "total_reviews",
        "total_shops",
    )

    # get min and max values for each type of analytics
    min_max = {
        "total_orders_amount": {
            "min": min([data["total_orders_amount"] for data in min_max_data]),
            "max": max([data["total_orders_amount"] for data in min_max_data]),
        },
        "total_orders": {
            "min": min([data["total_orders"] for data in min_max_data]),
            "max": max([data["total_orders"] for data in min_max_data]),
        },
        "total_reviews": {
            "min": min([data["total_reviews"] for data in min_max_data]),
            "max": max([data["total_reviews"] for data in min_max_data]),
        },
        "total_shops": {
            "min": min([data["total_shops"] for data in min_max_data]),
            "max": max([data["total_shops"] for data in min_max_data]),
        },
        "total_products": {
            "min": min([data["total_products"] for data in min_max_data]),
            "max": max([data["total_products"] for data in min_max_data]),
        },
    }

    # create a dictionary mapping category_id to analytics data
    analytics_dict = {data["category_id"]: data for data in analytics_data}

    # recursive function to build the tree
    def build_tree(category_id, type):
        category = category_dict[category_id]
        analytics = analytics_dict.get(category_id, {})
        children = children_map.get(category_id, [])
        res = {
            "categoryId": category_id,
            "title": category["title"],
            "title_ru": category["title_ru"],
            "analytics": analytics.get(type, 0),
            "children": [build_tree(child["categoryId"], type) for child in children],
        }

        # if children is empty remove it
        if len(res["children"]) == 0:
            del res["children"]
        return res

    # build the tree starting from the root
    category_tree_revenue = build_tree(1, type="total_orders_amount")
    category_tree_orders = build_tree(1, type="total_orders")
    category_tree_reviews = build_tree(1, type="total_reviews")
    category_tree_shops = build_tree(1, type="total_shops")
    category_tree_products = build_tree(1, type="total_products")

    # store in cache
    # cache.set("category_tree_data", category_tree, timeout=60 * 60 * 48)  # 48 hours
    # print("revenue tree: ", category_tree_revenue)

    cache.set(
        "category_tree_revenue",
        {"data": category_tree_revenue, "min_max": min_max["total_orders_amount"]},
        timeout=60 * 60 * 48,
    )  # 48 hours

    cache.set(
        "category_tree_orders",
        {"data": category_tree_orders, "min_max": min_max["total_orders"]},
        timeout=60 * 60 * 48,
    )  # 48 hours
    cache.set(
        "category_tree_reviews",
        {"data": category_tree_reviews, "min_max": min_max["total_reviews"]},
        timeout=60 * 60 * 48,
    )  # 48 hours
    cache.set(
        "category_tree_shops", {"data": category_tree_shops, "min_max": min_max["total_shops"]}, timeout=60 * 60 * 48
    )  # 48 hours
    cache.set(
        "category_tree_products",
        {"data": category_tree_products, "min_max": min_max["total_products"]},
        timeout=60 * 60 * 48,
    )  # 48 hours


# psql -h db-postgresql-blr1-80747-do-user-14120836-0.b.db.ondigitalocean.com -d defaultdb -U doadmin -p 25060
def create_materialized_view(date_pretty_str):
    # drop product analytics materialized view if exists
    drop_materialized_view()
    # drop sku analytics view if exists
    drop_sku_analytics_view()
    # drop product_avg_purchase_price_view if exists
    drop_product_avg_purchase_price_view()
    # drop product analytics monthly materialized view if exists
    # drop_product_analytics_monthly_materialized_view()
    create_product_analytics_monthly_materialized_view(date_pretty_str)

    # drop_product_analytics_weekly_materialized_view()
    create_product_analytics_weekly_materialized_view(date_pretty_str)

    create_sku_analytics_materialized_view(date_pretty_str)
    # create product avg purchase price view
    create_product_avg_purchase_price_view(date_pretty_str)
    # create product analytics monthly materialized view

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE MATERIALIZED VIEW product_sku_analytics AS
            SELECT
                pa.date_pretty,
                pa.product_id,
                p.title AS product_title,
                p.created_at AS product_created_at,
                p.title_ru AS product_title_ru,
                p.category_id,
                c.title AS category_title,
                c.title_ru AS category_title_ru,
                p.characteristics AS product_characteristics,
                p.photos,
                sh.title AS shop_title,
                sh.link AS shop_link,
                pa.available_amount AS product_available_amount,
                pa.orders_amount,
                pa.reviews_amount,
                pa.orders_money,
                pa.rating,
                pa.position_in_category,
                pa.position_in_shop,
                pa.position,
                jsonb_agg(
                    json_build_object(
                        'badge_text', b.text,
                        'badge_bg_color', b.background_color,
                        'badge_text_color', b.text_color
                    )
                )::text AS badges,
                COALESCE(sa.sku_analytics, '[]') AS sku_analytics,
                COALESCE(avp.avg_purchase_price, 0) AS avg_purchase_price,
                pam.diff_orders_money AS diff_orders_money,  -- added from product_analytics_monthly
                pam.diff_orders_amount AS diff_orders_amount,  -- added from product_analytics_monthly
                pam.diff_reviews_amount AS diff_reviews_amount,  -- added from product_analytics_monthly
                paw.weekly_orders_money AS weekly_orders_money,  -- added from product_analytics_weekly
                paw.weekly_orders_amount AS weekly_orders_amount,  -- added from product_analytics_weekly
                paw.weekly_reviews_amount AS weekly_reviews_amount  -- added from product_analytics_weekly
            FROM
                product_productanalytics pa
                JOIN product_product p ON pa.product_id = p.product_id
                JOIN category_category c ON p.category_id = c."categoryId"
                JOIN shop_shop sh ON p.shop_id = sh.seller_id
                LEFT JOIN product_productanalytics_badges pb ON pa.id = pb.productanalytics_id
                LEFT JOIN badge_badge b ON pb.badge_id = b.badge_id
                LEFT JOIN sku_analytics_view sa ON pa.product_id = sa.product_id
                LEFT JOIN product_avg_purchase_price_view avp ON pa.product_id = avp.product_id
                LEFT JOIN product_analytics_monthly pam ON pa.product_id = pam.product_id
                LEFT JOIN product_analytics_weekly paw ON pa.product_id = paw.product_id
            WHERE
                pa.date_pretty = '{date_pretty_str}'
            GROUP BY
                pa.date_pretty,
                pa.product_id,
                p.title,
                p.created_at,
                p.title_ru,
                p.category_id,
                c.title,
                c.title_ru,
                p.characteristics,
                p.photos,
                sh.title,
                sh.link,
                pa.available_amount,
                pa.orders_amount,
                pa.orders_money,
                pa.reviews_amount,
                pa.rating,
                pa.position_in_category,
                pa.position_in_shop,
                pa.position,
                sa.sku_analytics,
                avp.avg_purchase_price,
                pam.diff_orders_money,  -- group by these new columns as well
                pam.diff_orders_amount,
                pam.diff_reviews_amount,
                paw.weekly_orders_money,
                paw.weekly_orders_amount,
                paw.weekly_reviews_amount;
            """
        )

    # drop sku analytics materialized view if exists
    # drop_sku_analytics_view()
    # drop product_avg_purchase_price_view if exists
    # drop_product_avg_purchase_price_view()


def create_sku_analytics_materialized_view(date_pretty_str):
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE MATERIALIZED VIEW sku_analytics_view AS
            SELECT
                s.product_id,
                json_agg(
                    json_build_object(
                        'sku_id', sa.sku_id,
                        'available_amount', sa.available_amount,
                        'orders_amount', sa.orders_amount,
                        'purchase_price', sa.purchase_price,
                        'full_price', sa.full_price
                    )
                )::text AS sku_analytics
            FROM
                sku_skuanalytics sa
                JOIN sku_sku s ON sa.sku_id = s.sku
            WHERE
                sa.date_pretty = '{date_pretty_str}'
            GROUP BY
                s.product_id
            """
        )


def create_product_avg_purchase_price_view(date_pretty_str):
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            CREATE MATERIALIZED VIEW product_avg_purchase_price_view AS
            SELECT
                s.product_id,
                AVG(sa.purchase_price) AS avg_purchase_price
            FROM
                sku_skuanalytics sa
                JOIN sku_sku s ON sa.sku_id = s.sku
            WHERE
                sa.date_pretty = '{date_pretty_str}'
            GROUP BY
                s.product_id
            """
        )


def create_product_analytics_monthly_materialized_view(date_pretty):
    thirty_days_ago = (
        timezone.make_aware(datetime.now() - timedelta(days=30))
        .astimezone(pytz.timezone("Asia/Tashkent"))
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )

    # If date_pretty is a datetime object, convert it to a string
    if isinstance(date_pretty, datetime):
        date_pretty = date_pretty.strftime("%Y-%m-%d")

    with connection.cursor() as cursor:
        # Drop the materialized view if it exists
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS product_analytics_monthly;")

        cursor.execute(
            """
            CREATE MATERIALIZED VIEW product_analytics_monthly AS
            WITH LatestEntries AS (
                SELECT
                    product_id,
                    MAX(created_at) as latest_date
                FROM
                    product_productanalytics
                WHERE
                    created_at <= %s
                GROUP BY
                    product_id
            )

            , CurrentEntries AS (
                SELECT
                    product_id,
                    orders_amount AS current_orders_amount,
                    orders_money AS current_orders_money,
                    reviews_amount AS current_reviews_amount
                FROM
                    product_productanalytics
                WHERE
                    date_pretty = %s
            )

            SELECT
                CE.product_id,
                LE.latest_date AS latest_date_30_days_ago,
                COALESCE(PA.orders_amount, 0) AS orders_amount_30_days_ago,
                COALESCE(PA.orders_money, 0) AS orders_money_30_days_ago,
                COALESCE(PA.reviews_amount, 0) AS reviews_amount_30_days_ago,
                CE.current_orders_amount,
                CE.current_orders_money,
                CE.current_reviews_amount,
                GREATEST(CE.current_orders_amount - COALESCE(PA.orders_amount, 0), 0) AS diff_orders_amount,  -- use GREATEST here
                GREATEST(CE.current_orders_money - COALESCE(PA.orders_money, 0), 0) AS diff_orders_money,  -- and here
                GREATEST(CE.current_reviews_amount - COALESCE(PA.reviews_amount, 0), 0) AS diff_reviews_amount  -- and here
            FROM
                CurrentEntries CE
            LEFT JOIN
                LatestEntries LE ON CE.product_id = LE.product_id
            LEFT JOIN
                product_productanalytics PA ON LE.product_id = PA.product_id AND LE.latest_date = PA.created_at;
            """,
            [thirty_days_ago, date_pretty],
        )


def update_monthly_for_shops(date_pretty):
    create_shop_analytics_monthly_materialized_view(date_pretty)
    update_shop_analytics_from_materialized_view(date_pretty)


def update_shop_analytics_from_materialized_view(date_pretty):
    # If date_pretty is a datetime object, convert it to a string
    if isinstance(date_pretty, datetime):
        date_pretty = date_pretty.strftime("%Y-%m-%d")

    with connection.cursor() as cursor:
        cursor.execute(
            """
            UPDATE shop_shopanalytics sa
            SET
                monthly_total_orders = mv.monthly_total_orders,
                monthly_total_revenue = mv.monthly_total_revenue
            FROM shop_analytics_monthly mv
            WHERE
                sa.shop_id = mv.shop_id
                AND sa.date_pretty = %s
            """,
            [date_pretty],
        )


def create_shop_analytics_monthly_materialized_view(date_pretty):
    thirty_days_ago = (
        timezone.make_aware(datetime.now() - timedelta(days=30))
        .astimezone(pytz.timezone("Asia/Tashkent"))
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )

    # If date_pretty is a datetime object, convert it to a string
    if isinstance(date_pretty, datetime):
        date_pretty = date_pretty.strftime("%Y-%m-%d")

    with connection.cursor() as cursor:
        # Drop the materialized view if it exists
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS shop_analytics_monthly;")

        cursor.execute(
            """
            CREATE MATERIALIZED VIEW shop_analytics_monthly AS
            WITH LatestEntries AS (
                SELECT
                    shop_id,
                    MAX(created_at) as latest_date
                FROM
                    shop_shopanalytics
                WHERE
                    created_at <= %s
                GROUP BY
                    shop_id
            )

            , CurrentEntries AS (
                SELECT
                    shop_id,
                    total_orders AS current_total_orders,
                    total_revenue AS current_total_revenue
                FROM
                    shop_shopanalytics
                WHERE
                    date_pretty = %s
            )

            SELECT
                CE.shop_id,
                LE.latest_date AS latest_date_30_days_ago,
                COALESCE(PA.total_orders, 0) AS orders_amount_30_days_ago,
                COALESCE(PA.total_revenue, 0) AS orders_money_30_days_ago,
                CE.current_total_orders,
                CE.current_total_revenue,
                GREATEST(CE.current_total_orders - COALESCE(PA.total_orders, 0), 0) AS monthly_total_orders,  -- use GREATEST here
                GREATEST(CE.current_total_revenue - COALESCE(PA.total_revenue, 0), 0) AS monthly_total_revenue  -- and here
            FROM
                CurrentEntries CE
            LEFT JOIN
                LatestEntries LE ON CE.shop_id = LE.shop_id
            LEFT JOIN
                shop_shopanalytics PA ON LE.shop_id = PA.shop_id AND LE.latest_date = PA.created_at;
            """,
            [thirty_days_ago, date_pretty],
        )


def create_product_analytics_weekly_materialized_view(date_pretty):
    thirty_days_ago = (
        timezone.make_aware(datetime.now() - timedelta(days=7))
        .astimezone(pytz.timezone("Asia/Tashkent"))
        .replace(hour=0, minute=0, second=0, microsecond=0)
    )

    # If date_pretty is a datetime object, convert it to a string
    if isinstance(date_pretty, datetime):
        date_pretty = date_pretty.strftime("%Y-%m-%d")

    with connection.cursor() as cursor:
        # Drop the materialized view if it exists
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS product_analytics_weekly;")

        cursor.execute(
            """
            CREATE MATERIALIZED VIEW product_analytics_weekly AS
            WITH LatestEntries AS (
                SELECT
                    product_id,
                    MAX(created_at) as latest_date
                FROM
                    product_productanalytics
                WHERE
                    created_at <= %s
                GROUP BY
                    product_id
            )

            , CurrentEntries AS (
                SELECT
                    product_id,
                    orders_amount AS current_orders_amount,
                    orders_money AS current_orders_money,
                    reviews_amount AS current_reviews_amount
                FROM
                    product_productanalytics
                WHERE
                    date_pretty = %s
            )

            SELECT
                CE.product_id,
                LE.latest_date AS latest_date_7_days_ago,
                COALESCE(PA.orders_amount, 0) AS orders_amount_7_days_ago,
                COALESCE(PA.orders_money, 0) AS orders_money_7_days_ago,
                COALESCE(PA.reviews_amount, 0) AS reviews_amount_7_days_ago,
                CE.current_orders_amount,
                CE.current_orders_money,
                CE.current_reviews_amount,
                GREATEST(CE.current_orders_amount - COALESCE(PA.orders_amount, 0), 0) AS weekly_orders_amount,  -- use GREATEST here
                GREATEST(CE.current_orders_money - COALESCE(PA.orders_money, 0), 0) AS weekly_orders_money,  -- and here
                GREATEST(CE.current_reviews_amount - COALESCE(PA.reviews_amount, 0), 0) AS weekly_reviews_amount  -- and here
            FROM
                CurrentEntries CE
            LEFT JOIN
                LatestEntries LE ON CE.product_id = LE.product_id
            LEFT JOIN
                product_productanalytics PA ON LE.product_id = PA.product_id AND LE.latest_date = PA.created_at;
            """,
            [thirty_days_ago, date_pretty],
        )


def vacuum_table(table_name):
    with connection.cursor() as cursor:
        cursor.execute(f"VACUUM (VERBOSE, ANALYZE) {table_name};")


def drop_product_analytics_weekly_materialized_view():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DROP MATERIALIZED VIEW IF EXISTS product_analytics_weekly
            """
        )


def drop_product_analytics_monthly_materialized_view():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DROP MATERIALIZED VIEW IF EXISTS product_analytics_monthly
            """
        )


def drop_product_avg_purchase_price_view():
    with connection.cursor() as cursor:
        cursor.execute(
            """
            DROP MATERIALIZED VIEW IF EXISTS product_avg_purchase_price_view
            """
        )


def drop_materialized_view():
    with connection.cursor() as cursor:
        cursor.execute(
            """
        DROP MATERIALIZED VIEW IF EXISTS product_sku_analytics;
        """
        )


def drop_sku_analytics_view():
    with connection.cursor() as cursor:
        cursor.execute(
            """
        DROP MATERIALIZED VIEW IF EXISTS sku_analytics_view;
        """
        )


def bulk_remove_duplicate_product_analytics(date_pretty):
    # SQL Query to get the most recent ProductAnalytics for each product on given date_pretty
    sql = f"""
    SELECT DISTINCT ON (product_id)
        id
    FROM
        product_productanalytics
    WHERE
        date_pretty = '{date_pretty}'
    ORDER BY
        product_id, created_at DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        keep_ids = [row[0] for row in cursor.fetchall()]

    # Then, get all ProductAnalytics objects for given date_pretty but exclude those whose id are in keep_ids
    pa_to_delete = ProductAnalytics.objects.filter(date_pretty=date_pretty).exclude(id__in=keep_ids)

    # Count the number of entries about to be deleted
    delete_count = pa_to_delete.count()
    print(f"About to delete {delete_count} duplicate ProductAnalytics entries for {date_pretty}")

    # Execute the delete operation
    pa_to_delete.delete()
    print(f"Deleted {delete_count} duplicate ProductAnalytics entries for {date_pretty}")


def bulk_remove_duplicate_shop_analytics(date_pretty):
    # SQL Query to get the most recent ShopAnalytics for each shop on given date_pretty
    sql = f"""
    SELECT DISTINCT ON (shop_id)
        id
    FROM
        shop_shopanalytics
    WHERE
        date_pretty = '{date_pretty}'
    ORDER BY
        shop_id, created_at DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        keep_ids = [row[0] for row in cursor.fetchall()]

    # Then, get all ShopAnalytics objects for given date_pretty but exclude those whose id are in keep_ids
    sa_to_delete = ShopAnalytics.objects.filter(date_pretty=date_pretty).exclude(id__in=keep_ids)

    # Count the number of entries about to be deleted
    delete_count = sa_to_delete.count()
    print(f"About to delete {delete_count} duplicate ShopAnalytics entries for {date_pretty}")

    # Execute the delete operation
    sa_to_delete.delete()
    print(f"Deleted {delete_count} duplicate ShopAnalytics entries for {date_pretty}")


def bulk_remove_duplicate_sku_analytics(date_pretty):
    # SQL Query to get the most recent ShopAnalytics for each shop on given date_pretty
    sql = f"""
    SELECT DISTINCT ON (sku_id)
        id
    FROM
        sku_skuanalytics
    WHERE
        date_pretty = '{date_pretty}'
    ORDER BY
        sku_id, created_at DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        keep_ids = [row[0] for row in cursor.fetchall()]

    # Then, get all SkuAnalytics objects for given date_pretty but exclude those whose id are in keep_ids
    sa_to_delete = SkuAnalytics.objects.filter(date_pretty=date_pretty).exclude(id__in=keep_ids)

    # Count the number of entries about to be deleted
    delete_count = sa_to_delete.count()
    print(f"About to delete {delete_count} duplicate SkuAnalytics entries for {date_pretty}")

    # Execute the delete operation
    sa_to_delete.delete()
    print(f"Deleted {delete_count} duplicate ShopAnalytics entries for {date_pretty}")


def bulk_remove_duplicate_category_analytics(date_pretty):
    # SQL Query to get the most recent CategoryAnalytics for each category on given date_pretty
    sql = f"""
    SELECT DISTINCT ON (category_id)
        id
    FROM
        category_categoryanalytics
    WHERE
        date_pretty = '{date_pretty}'
    ORDER BY
        category_id, created_at DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        keep_ids = [row[0] for row in cursor.fetchall()]

    # Then, get all CategoryAnalytics objects for given date_pretty but exclude those whose id are in keep_ids
    ca_to_delete = CategoryAnalytics.objects.filter(date_pretty=date_pretty).exclude(id__in=keep_ids)

    # Count the number of entries about to be deleted
    delete_count = ca_to_delete.count()
    print(f"About to delete {delete_count} duplicate CategoryAnalytics entries for {date_pretty}")

    # Execute the delete operation
    ca_to_delete.delete()
    print(f"Deleted {delete_count} duplicate CategoryAnalytics entries for {date_pretty}")


# def get_categories_with_less_than_n_products_test(n):
#     """
#     Get categories with less than n products
#     Args:
#         n (int):   number of products
#     Returns:
#         Array: [{
#                 categoryId: total_products
#             }]
#     """
#     try:
#         # all_categories = sync_to_async(Category.objects.all().order_by("categoryId"))
#         # order_by("categoryId")
#         all_categories = get_categories_tree()
#         print(
#             f"getCategoriesWithLessThanNProducts: all category analytics fetched {len(all_category_analytics)}",
#         )
#         # 1. make dict of all categories: key - categoryId, value - total_products and children
#         # children is ManyToManey field to itself. We need to get list children's categoryId
#         all_categories_dict = {}

#         for category in all_category_analytics:
#             all_categories_dict[category.category.categoryId] = {
#                 "categoryId": category.category.categoryId,
#                 "total_products": category.total_products,
#                 "children": list(category.category.child_categories.values_list("categoryId", flat=True)),
#             }

#         filtered_categories = []

#         filter_categories(all_categories_dict[1], all_categories_dict, filtered_categories, n, {})

#         print(f"getCategoriesWithLessThanNProducts: {len(filtered_categories)} categories found")

#         # calculate total products for all filtered categories
#         total = 0
#         for category in filtered_categories:
#             total += category["total_products"]

#         print(f"getCategoriesWithLessThanNProducts: {total} products found")

#         return filtered_categories
#     except Exception as e:
#         print(f"Error in getCategoriesWithLessThanNProducts: {e}")
#         print(traceback.print_exc())
#         return None
