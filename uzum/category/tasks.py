
import json
import time
from collections import Counter
from datetime import datetime

import pytz
from asgiref.sync import async_to_sync

from config import celery_app
from uzum.category.analytics import update_analytics
from uzum.category.duplicate_remove import (
    bulk_remove_duplicate_category_analytics,
    bulk_remove_duplicate_product_analytics,
    bulk_remove_duplicate_shop_analytics, bulk_remove_duplicate_sku_analytics)
from uzum.category.failed_fetch import fetch_popular_seaches_from_uzum, fetch_product_ids
from uzum.category.materialized_views import (
    create_shop_analytics_monthly_materialized_view,
    update_shop_analytics_from_materialized_view)
from uzum.category.models import Category, CategoryAnalytics
from uzum.category.tree import (update_category_tree,
                                update_category_tree_with_data,
                                update_category_tree_with_monthly_data,
                                update_category_tree_with_weekly_data)
from uzum.category.utils import (update_all_category_parents,
                                 update_category_with_sales, vacuum_table)
from uzum.jobs.campaign.main import update_or_create_campaigns
from uzum.jobs.category.main import create_and_update_categories
from uzum.jobs.category.MultiEntry import \
    get_categories_with_less_than_n_products
from uzum.jobs.category.utils import add_russian_titles
from uzum.jobs.constants import MAX_ID_COUNT, PAGE_SIZE
from uzum.jobs.product.fetch_details import get_product_details_via_ids
from uzum.jobs.product.fetch_ids import get_all_product_ids_from_uzum
from uzum.jobs.product.MultiEntry import create_products_from_api
from uzum.product.models import create_product_latestanalytics
from uzum.review.models import PopularSeaches
from uzum.users.tasks import send_reports_to_all
from uzum.utils.general import get_day_before_pretty, get_today_pretty


@celery_app.task(
    name="update_uzum_data",
)
def update_uzum_data(args=None, **kwargs):
    # before starting data creation, vacuum all tables
    vacuum_table("category_categoryanalytics")
    vacuum_table("product_productanalytics")
    vacuum_table("shop_shopanalytics")
    vacuum_table("sku_skuanalytics")

    # get today's date
    date_pretty = get_today_pretty()

    print(get_today_pretty())
    print(datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%H:%M:%S" + " - " + "%d/%m/%Y"))

    # create_and_update_categories()
    start = time.time()
    # update_all_category_parents()
    # Category.update_descendants()
    # Category.update_ancestors_bulk()
    # print("Category parents updated: ", time.time() - start)

    # root = CategoryAnalytics.objects.filter(category__categoryId=1, date_pretty=get_today_pretty())
    # print("total_products: ", root[0].total_products)

    # # 1. Get all categories which have less than N products
    # categories_filtered = get_categories_with_less_than_n_products(MAX_ID_COUNT)

    # product_ids: list[int] = []
    # async_to_sync(get_all_product_ids_from_uzum)(
    #     categories_filtered,
    #     product_ids,
    #     page_size=PAGE_SIZE,
    # )

    # print(f"Total product ids: {len(product_ids)}")

    # product_ids = list(set(product_ids))

    # product_campaigns, product_associations, shop_association = update_or_create_campaigns()

    # shop_analytics_done = {}

    # BATCH_SIZE = 10_000

    # # Create Latest Analytics of products ->  used for calculating orders_money for product analytics
    # start = time.time()
    # create_product_latestanalytics(get_day_before_pretty(date_pretty))
    # print(f"Latest Analytics created in {time.time() - start} seconds")

    # category_sales_map = {
    #     analytics.category.categoryId: {
    #         "products_with_sales": set(),
    #         "shops_with_sales": set(),
    #     }
    #     for analytics in CategoryAnalytics.objects.filter(date_pretty=date_pretty).prefetch_related("category")
    # }

    # for i in range(0, len(product_ids), BATCH_SIZE):
    #     products_api: list[dict] = []
    #     print(f"{i}/{len(product_ids)}")
    #     async_to_sync(get_product_details_via_ids)(product_ids[i : i + BATCH_SIZE], products_api)
    #     create_products_from_api(products_api, product_campaigns, shop_analytics_done, category_sales_map)
    #     time.sleep(10)
    #     del products_api
    # Category.update_descendants()

    # time.sleep(10)
    # try:
    #     fetch_product_ids(date_pretty, product_ids)
    # except Exception as e:
    #     print("Error in remaining fetch_product_ids:", e)
    # # add russian titles to all products
    # add_russian_titles()

    # # create popular searches
    # create_todays_searches()

    # # remove duplicate analytics
    # bulk_remove_duplicate_category_analytics(date_pretty)
    # bulk_remove_duplicate_product_analytics(date_pretty)
    # bulk_remove_duplicate_shop_analytics(date_pretty)
    # bulk_remove_duplicate_sku_analytics(date_pretty)

    # # ANALYTICS STARTS HERE
    # update_category_with_sales(category_sales_map, date_pretty)

    # start = time.time()
    # update_analytics(date_pretty)
    # print(f"All Analytics updated in {time.time() - start} seconds")

    # start = time.time()
    # send_reports_to_all()
    # print(f"Reports sent in {time.time() - start} seconds")

    # update_category_tree_with_monthly_data(date_pretty)
    # update_category_tree_with_weekly_data(date_pretty)
    # update_category_tree_with_data(date_pretty)
    # update_category_tree(date_pretty)
    return True


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

