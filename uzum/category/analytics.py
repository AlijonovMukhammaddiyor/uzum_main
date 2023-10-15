
import time
import traceback
from datetime import datetime

import pytz
from django.db import connection

from uzum.banner.models import Banner
from uzum.category.materialized_views import (
    create_combined_shop_analytics_materialized_view, create_materialized_view, create_shop_analytics_monthly_materialized_view,
    update_shop_analytics_from_materialized_view)
from uzum.category.models import CategoryAnalytics
from uzum.category.utils import vacuum_table
from uzum.product.models import (ProductAnalytics,
                                 create_product_latestanalytics)
from uzum.shop.models import ShopAnalytics
from uzum.sku.models import (SkuAnalytics, create_sku_latestanalytics,
                             set_orders_amount_sku)
from uzum.utils.general import get_day_before_pretty


def update_analytics(date_pretty: str):
    """
    STEPS:
    1. Vacuum all tables to free up space
    2. Start from SKU
    """
    try:
        start = time.time()
        vacuum_table("category_categoryanalytics")
        vacuum_table("product_productanalytics")
        vacuum_table("shop_shopanalytics")
        vacuum_table("sku_skuanalytics")
        print(f"Vacuumed all tables in {time.time() - start} seconds")

        # SKU ANALYTICS
        # 1. Latest Product Analytics Materialized View is already up to date
        # 2. Create Lates SKU Analytics Materialized View
        create_sku_latestanalytics(date_pretty=get_day_before_pretty(date_pretty))
        # 3. Set real_orders_amount of product analytics
        ProductAnalytics.update_real_orders_amount(date_pretty)  # this needs product latest analytics view
        # 4. Update SKU delta_available_amount
        SkuAnalytics.update_delta_available_amount(date_pretty)
        # 5. Now, I can calculate the SKU orders_amount
        set_orders_amount_sku(date_pretty)
        # after it is set, we can set orders_money
        SkuAnalytics.update_orders_money(date_pretty)
        # SKU IS DONE

        # UPDATE PRODUCT ANALYTICS
        # 1. Set daily_revenue - it uses orders_money from SKU
        ProductAnalytics.set_daily_revenue(date_pretty)

        start = time.time()
        ProductAnalytics.update_analytics(date_pretty)
        create_materialized_view(date_pretty)

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
        # update_monthly_for_shops(date_pretty)

        print("Creating Materialized View...")
        start = time.time()

        print(f"Materialized View created in {time.time() - start} seconds")
        print("Setting banners...")
        Banner.set_products()
        create_combined_shop_analytics_materialized_view(date_pretty)

    except Exception as e:
        print("Error in update_analytics:", e)
        traceback.print_exc()


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

def update_monthly_for_shops(date_pretty):
    # create_shop_analytics_monthly_materialized_view(date_pretty)
    # update_shop_analytics_from_materialized_view(date_pretty)
    pass

