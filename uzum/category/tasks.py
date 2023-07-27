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
from django.db import connection, transaction

from config import celery_app
from uzum.banner.models import Banner
from uzum.category.models import Category, CategoryAnalytics
from uzum.jobs.campaign.main import update_or_create_campaigns
from uzum.jobs.campaign.utils import associate_with_shop_or_product
from uzum.jobs.category.main import create_and_update_categories
from uzum.jobs.category.MultiEntry import get_categories_with_less_than_n_products
from uzum.jobs.constants import CATEGORIES_HEADER, MAX_ID_COUNT, PAGE_SIZE, POPULAR_SEARCHES_PAYLOAD
from uzum.jobs.helpers import generateUUID, get_random_user_agent
from uzum.jobs.product.fetch_details import get_product_details_via_ids
from uzum.jobs.product.fetch_ids import get_all_product_ids_from_uzum
from uzum.jobs.product.MultiEntry import create_products_from_api
from uzum.product.models import Product, ProductAnalytics
from uzum.review.models import PopularSeaches
from uzum.shop.models import Shop, ShopAnalytics
from uzum.sku.models import SkuAnalytics
from uzum.utils.general import get_today_pretty


@celery_app.task(
    name="update_uzum_data",
)
def update_uzum_data(args=None, **kwargs):
    print(get_today_pretty())
    date_pretty = get_today_pretty()
    print(datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%H:%M:%S" + " - " + "%d/%m/%Y"))

    create_and_update_categories()
    # await create_and_update_products()

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

    for i in range(0, len(product_ids), BATCH_SIZE):
        products_api: list[dict] = []
        print(f"{i}/{len(product_ids)}")
        async_to_sync(get_product_details_via_ids)(product_ids[i : i + BATCH_SIZE], products_api)
        create_products_from_api(products_api, product_campaigns, shop_analytics_done)
        time.sleep(30)
        del products_api

    time.sleep(600)

    # fetch_product_ids()

    time.sleep(30)

    print("Setting banners...", product_associations, shop_association)
    print(product_associations, shop_association)
    bulk_remove_duplicate_product_analytics(date_pretty)

    for product_id, banners in product_associations.items():
        try:
            product = Product.objects.get(product_id=product_id)
            product_analytics = ProductAnalytics.objects.filter(product=product, date_pretty=get_today_pretty())

            if len(product_analytics) > 0:
                # get the most recently created analytics
                product_analytics = product_analytics.order_by("-created_at").first()

            product_analytics.banners.set(banners)
            product_analytics.save()

            print(f"Product {product.title} banners set")
        except Exception as e:
            print("Error in setting banner(s): ", e)

    for link, banners in shop_association.items():
        try:
            shop_an = ShopAnalytics.objects.filter(shop=Shop.objects.get(link=link), date_pretty=get_today_pretty())

            if len(shop_an) > 0:
                shop_an = shop_an.order_by("-created_at").first()

            if len(shop_an) == 0:
                continue
            target = shop_an.order_by("-created_at").first()  # get most recently created analytics
            target.banners.set(banners)
            target.save()

            print(f"Shop {link} banner(s) set")
        except Exception as e:
            print("Error in setting shop banner(s): ", e)

    create_todays_searches()

    bulk_remove_duplicate_category_analytics(date_pretty)
    bulk_remove_duplicate_product_analytics(date_pretty)
    bulk_remove_duplicate_shop_analytics(date_pretty)
    bulk_remove_duplicate_sku_analytics(date_pretty)

    print("Updating Category Descendants...")
    start = time.time()
    Category.update_descendants()
    print(f"Category Descendants updated in {time.time() - start} seconds")

    print("Updating Analytics...")
    start = time.time()
    update_analytics(date_pretty)
    print(f"Analytics updated in {time.time() - start} seconds")

    print("Creating Materialized View...")
    start = time.time()
    create_materialized_view(date_pretty)
    print(f"Materialized View created in {time.time() - start} seconds")

    print("Updating category tree...")
    update_category_tree()

    update_category_tree_with_data()
    print("Uzum data updated...")
    return True


def update_analytics(date_pretty: str):
    try:
        start = time.time()
        ProductAnalytics.update_analytics(date_pretty)
        print(f"ProductAnalytics updated in {time.time() - start} seconds")
        start = time.time()
        ShopAnalytics.update_analytics(date_pretty)
        print(f"ShopAnalytics updated in {time.time() - start} seconds")
        start = time.time()
        CategoryAnalytics.update_analytics(date_pretty)
        print(f"CategoryAnalytics updated in {time.time() - start} seconds")
    except Exception as e:
        print("Error in update_analytics:", e)
        traceback.print_exc()


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

    categories_filtered = get_categories_with_less_than_n_products(MAX_ID_COUNT)
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

    for i in range(0, len(unfetched_product_ids), BATCH_SIZE):
        products_api: list[dict] = []
        print(
            f"Processing batch {i // BATCH_SIZE + 1}/{(len(unfetched_product_ids) + BATCH_SIZE - 1) // BATCH_SIZE}..."
        )
        async_to_sync(get_product_details_via_ids)(unfetched_product_ids[i : i + BATCH_SIZE], products_api)

        # Wrap database interaction in a transaction
        with transaction.atomic():
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


def update_category_tree_with_data():
    categories = Category.objects.values("categoryId", "title", "parent_id")

    # first create a dictionary mapping ids to category data
    category_dict = {category["categoryId"]: category for category in categories}

    # then build a mapping from parent_id to a list of its children
    children_map = {}
    for category in categories:
        children_map.setdefault(category["parent_id"], []).append(category)

    # get analytics data
    analytics_data = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty()).values(
        "category_id",
        "category__title",
        "total_orders_amount",
        "total_orders",
        "total_products",
        "total_reviews",
        "total_shops",
    )

    min_max_data = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty(), category__children=None).values(
        "category_id",
        "category__title",
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
    # create sku analytics view
    create_sku_analytics_materialized_view(date_pretty_str)
    # create product avg purchase price view
    create_product_avg_purchase_price_view(date_pretty_str)

    with connection.cursor() as cursor:
        cursor.execute(
            f"""
        CREATE MATERIALIZED VIEW product_sku_analytics AS
        SELECT
            pa.date_pretty,
            pa.product_id,
            p.title AS product_title,
            p.category_id,
            c.title AS category_title,  -- Added category_title here
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
            COALESCE(sa.sku_analytics, '[]') AS sku_analytics,  -- Added sku_analytics
            COALESCE(avp.avg_purchase_price, 0) AS avg_purchase_price  -- Added avg_purchase_price here
        FROM
            product_productanalytics pa
            JOIN product_product p ON pa.product_id = p.product_id
            JOIN category_category c ON p.category_id = c."categoryId"  -- Added join with category table here
            JOIN shop_shop sh ON p.shop_id = sh.seller_id
            LEFT JOIN product_productanalytics_badges pb ON pa.id = pb.productanalytics_id
            LEFT JOIN badge_badge b ON pb.badge_id = b.badge_id
            LEFT JOIN sku_analytics_view sa ON pa.product_id = sa.product_id
            LEFT JOIN product_avg_purchase_price_view avp ON pa.product_id = avp.product_id  -- Added join
        WHERE
            pa.date_pretty = '{date_pretty_str}'
        GROUP BY
            pa.date_pretty,
            pa.product_id,
            p.title,
            p.category_id,
            c.title,  -- Added category_title here
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
            avp.avg_purchase_price;  -- Added avg_purchase_price here
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
