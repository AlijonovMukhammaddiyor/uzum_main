import asyncio
from datetime import datetime

import pytz
from asgiref.sync import async_to_sync
from celery.schedules import crontab

from config import celery_app
from uzum.badge.models import Badge
from uzum.category.models import Category
from uzum.jobs.category.MultiEntry import get_categories_with_less_than_n_products
from uzum.jobs.category.main import create_and_update_categories
from uzum.jobs.constants import MAX_OFFSET, PAGE_SIZE
from uzum.jobs.product.MultiEntry import create_products_from_api
from uzum.jobs.product.main import create_and_update_products
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

    products_api = async_to_sync(create_and_update_products)(categories_filtered)

    create_products_from_api(products_api)
    # asyncio.create_task(create_and_update_products())
    print("Uzum data updated...")
    return True
