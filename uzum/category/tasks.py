import asyncio
from datetime import datetime
import time

import pytz
from asgiref.sync import async_to_sync
from celery.schedules import crontab

from config import celery_app
from uzum.badge.models import Badge
from uzum.category.models import Category
from uzum.jobs.campaign.main import update_or_create_campaigns
from uzum.jobs.category.MultiEntry import get_categories_with_less_than_n_products
from uzum.jobs.category.main import create_and_update_categories
from uzum.jobs.constants import MAX_OFFSET, PAGE_SIZE
from uzum.jobs.product.MultiEntry import create_products_from_api
from uzum.jobs.product.main import create_and_update_products
from uzum.jobs.product.utils import get_all_product_ids_from_uzum, get_product_details_via_ids
from uzum.product.models import Product, get_today_pretty
from uzum.shop.models import Shop


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

    product_campaigns = update_or_create_campaigns()

    # products_api = async_to_sync(create_and_update_products)(categories_filtered)
    # products_api = async_to_sync(create_and_update_products)(product_ids, 0, 30_000)
    products_api: list[dict] = []
    async_to_sync(get_product_details_via_ids)(product_ids[0:30_000], products_api)
    create_products_from_api(products_api, product_campaigns)

    print("Sleeping for 10 seconds...")
    time.sleep(30)

    products_api: list[dict] = []
    async_to_sync(get_product_details_via_ids)(product_ids[30_000:60_000], products_api)
    create_products_from_api(products_api, product_campaigns)

    print("Sleeping for 30 seconds...")
    time.sleep(30)

    products_api: list[dict] = []
    async_to_sync(get_product_details_via_ids)(product_ids[60_000:90_000], products_api)
    create_products_from_api(products_api, product_campaigns)
    print("Sleeping for 30 seconds...")
    time.sleep(30)

    products_api: list[dict] = []
    async_to_sync(get_product_details_via_ids)(product_ids[90_000:120_000], products_api)
    create_products_from_api(products_api, product_campaigns)

    print("Sleeping for 30 seconds...")
    time.sleep(30)

    products_api: list[dict] = []
    async_to_sync(get_product_details_via_ids)(product_ids[120_000:150_000], products_api)
    create_products_from_api(products_api, product_campaigns)

    print("Sleeping for 30 seconds...")
    time.sleep(30)

    products_api: list[dict] = []
    async_to_sync(get_product_details_via_ids)(product_ids[150_000:180_000], products_api)
    create_products_from_api(products_api, product_campaigns)

    print("Sleeping for 30 seconds...")
    time.sleep(30)

    # asyncio.create_task(create_and_update_products())
    print("Uzum data updated...")
    return True
