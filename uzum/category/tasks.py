import time
from datetime import datetime

import pytz
from asgiref.sync import async_to_sync

from config import celery_app
from uzum.jobs.campaign.main import update_or_create_campaigns
from uzum.jobs.category.main import create_and_update_categories
from uzum.jobs.category.MultiEntry import get_categories_with_less_than_n_products
from uzum.jobs.constants import MAX_OFFSET, PAGE_SIZE
from uzum.jobs.product.fetch_details import get_product_details_via_ids
from uzum.jobs.product.fetch_ids import get_all_product_ids_from_uzum
from uzum.jobs.product.MultiEntry import create_products_from_api
from uzum.product.models import get_today_pretty


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

    shop_analytics_done = {}

    BATCH_SIZE = 10_000

    for i in range(0, len(product_ids), BATCH_SIZE):
        products_api: list[dict] = []
        async_to_sync(get_product_details_via_ids)(product_ids[i:i + BATCH_SIZE], products_api)
        create_products_from_api(products_api, product_campaigns, shop_analytics_done)
        print(f"{i+1}. Sleeping for 30 seconds...")
        time.sleep(30)

    # asyncio.create_task(create_and_update_products())
    print("Uzum data updated...")
    return True
