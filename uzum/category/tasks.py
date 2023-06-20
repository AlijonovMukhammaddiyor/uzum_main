import time
from datetime import datetime

import pytz
from asgiref.sync import async_to_sync

from config import celery_app
from uzum.category.models import Category, CategoryAnalytics
from uzum.jobs.campaign.main import update_or_create_campaigns
from uzum.jobs.category.main import create_and_update_categories
from uzum.jobs.category.MultiEntry import get_categories_with_less_than_n_products
from uzum.jobs.constants import MAX_OFFSET, PAGE_SIZE
from uzum.jobs.product.fetch_details import get_product_details_via_ids
from uzum.jobs.product.fetch_ids import get_all_product_ids_from_uzum
from uzum.jobs.product.MultiEntry import create_products_from_api
from uzum.product.models import Product, ProductAnalytics, get_today_pretty
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

    print("Setting banners...", product_associations, shop_association)
    print(product_associations, shop_association)
    for product_id, banners in product_associations.items():
        try:
            product = Product.objects.get(product_id=product_id)
            product_analytics = ProductAnalytics.objects.get(product=product, date_pretty=get_today_pretty())

            if len(product_analytics) == 0:
                continue

            product_analytics = product_analytics.order_by(
                "-created_at"
            ).first()  # get most recently created analytics
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

    category_analytics = CategoryAnalytics.objects.filter(date_pretty=date_pretty)

    print("Setting total_products_with_sales and total_shops_with_sales...", len(category_analytics))

    # for category_an in category_analytics:
    #     category_an.set_total_products_with_sale()
    #     category_an.set_total_shops()
    #     category_an.set_total_orders()
    #     category_an.set_total_reviews()

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


# def fetch_products(url):
#     headers = CaseInsensitiveDict()
#     headers["Access-Control-Allow-Credentials"] = "true"
#     headers["Origin"] = "https://uzum.uz"
#     headers["Authority"] = "api.uzum.uz"
#     headers[
#         "User-Agent"
#     ] = "Mozilla/5.0 (Windows NT 10.0; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
#     headers["Referrer"] = "https://uzum.uz/"
#     headers["Access-Control-Allow-Origin"] = "https://uzum.uz"
#     headers["Authorization"] = "Basic YjJjLWZyb250OmNsaWVudFNlY3JldA=="
#     headers["x-lid"] = "25dc2cba-2d8e-4192-bac7-8f0df42cbdd5"
#     headers["Sec-Ch-Ua"] = "'Not.A/Brand';v='8', 'Chromium';v='114', 'Google Chrome';v='114'"
#     headers["Sec-Ch-Ua-Mobile"] = "?0"
#     headers["Sec-Ch-Ua-Platform"] = "'macOS'"
#     headers["Sec-Fetch-Dest"] = "empty"
#     headers["Sec-Fetch-Mode"] = "cors"
#     headers["Sec-Fetch-Site"] = "same-site"
#     resp = requests.get(url, headers=headers)

#     # print (resp.json())
#     return resp.json()
