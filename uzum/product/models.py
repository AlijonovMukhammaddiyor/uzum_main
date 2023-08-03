import traceback
import uuid

import numpy as np
import pandas as pd
from django.core.cache import cache
from django.db import connection, models
from django.utils import timezone
from uzum.utils.general import get_day_before_pretty, get_today_pretty
from datetime import datetime
import pytz


class Product(models.Model):
    product_id = models.IntegerField(unique=True, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    title = models.TextField(db_index=True)
    title_ru = models.TextField(default=None, null=True, blank=True, db_index=True)
    description = models.TextField(default=None, null=True, blank=True)
    adult = models.BooleanField(default=False)
    bonus_product = models.BooleanField(default=False)
    is_eco = models.BooleanField(default=False)
    is_perishable = models.BooleanField(default=False)
    volume_discount = models.IntegerField(default=None, null=True, blank=True)
    video = models.TextField(null=True, blank=True)

    shop = models.ForeignKey("shop.Shop", on_delete=models.DO_NOTHING, related_name="products", db_index=True)

    category = models.ForeignKey(
        "category.Category",
        on_delete=models.DO_NOTHING,
        related_name="products",
        db_index=True,
    )

    attributes = models.TextField(null=True, blank=True)  # json.dumps(attributes)
    comments = models.TextField(null=True, blank=True)  # json.dumps(comments)
    photos = models.TextField(null=True, blank=True)  # json.dumps(photos)
    characteristics = models.TextField(null=True, blank=True)  # json.dumps(characteristics)

    def __str__(self) -> str:
        return f"{self.product_id} - {self.title}"


class ProductAnalytics(models.Model):
    id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        primary_key=True,
    )
    product = models.ForeignKey(Product, on_delete=models.DO_NOTHING, related_name="analytics", db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    banners = models.ManyToManyField(
        "banner.Banner",
        # on_delete=models.DO_NOTHING, null=True, blank=True, related_name="products"
    )

    badges = models.ManyToManyField(
        "badge.Badge",
        related_name="products",
    )

    available_amount = models.IntegerField(default=0)
    reviews_amount = models.IntegerField(default=0)
    rating = models.FloatField(default=0)
    orders_amount = models.IntegerField(default=0, db_index=True)
    orders_money = models.FloatField(default=0.0, db_index=True)

    campaigns = models.ManyToManyField(
        "campaign.Campaign",
    )
    date_pretty = models.CharField(max_length=255, null=True, blank=True, db_index=True, default=get_today_pretty)
    position_in_shop = models.IntegerField(default=0, null=True, blank=True)
    position_in_category = models.IntegerField(default=0, null=True, blank=True)
    position = models.IntegerField(default=0, null=True, blank=True)
    average_purchase_price = models.IntegerField(default=0, null=True, blank=True)

    @staticmethod
    def set_positions(date_pretty=get_today_pretty()):
        try:
            # Sort product analytics by orders_amount for each shop and category separately
            with connection.cursor() as cursor:
                # Position in shop
                cursor.execute(
                    f"""
                    WITH ranked_products AS (
                        SELECT
                            pa.id,
                            RANK() OVER (
                                PARTITION BY p.shop_id
                                ORDER BY pa.orders_money DESC
                            ) as rank
                        FROM
                            product_productanalytics pa
                        INNER JOIN
                            product_product p ON pa.product_id = p.product_id
                        WHERE
                            pa.date_pretty = '{date_pretty}'
                    )
                    UPDATE
                        product_productanalytics
                    SET
                        position_in_shop = ranked_products.rank
                    FROM
                        ranked_products
                    WHERE
                        product_productanalytics.id = ranked_products.id;
                """
                )

            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    WITH ranked_products AS (
                        SELECT
                            pa.id,
                            RANK() OVER (
                                PARTITION BY p.category_id
                                ORDER BY pa.orders_money DESC
                            ) as rank
                        FROM
                            product_productanalytics pa
                        INNER JOIN
                            product_product p ON pa.product_id = p.product_id
                        WHERE
                            pa.date_pretty = '{date_pretty}'
                    )
                    UPDATE
                        product_productanalytics
                    SET
                        position_in_category = ranked_products.rank
                    FROM
                        ranked_products
                    WHERE
                        product_productanalytics.id = ranked_products.id;
                """
                )

            with connection.cursor() as cursor:
                cursor.execute(
                    f"""
                    WITH ranked_products AS (
                        SELECT
                            pa.id,
                            RANK() OVER (
                                ORDER BY pa.orders_money DESC
                            ) as rank
                        FROM
                            product_productanalytics pa
                        WHERE
                            pa.date_pretty = '{date_pretty}'
                    )
                    UPDATE
                        product_productanalytics
                    SET
                        position = ranked_products.rank
                    FROM
                        ranked_products
                    WHERE
                        product_productanalytics.id = ranked_products.id;
                """
                )

        except Exception as e:
            print(e, "error in set_position_in_shop")

    def get_orders_amount_in_day(self, date=None):
        """
        Get orders amount in a day.
        Get yesterday's analytics and subtract today's orders_amount from it.
        If there is no yesterday's analytics, return today's orders_amount.
        """
        try:
            # get the latest analytics of this product
            yesterday_pretty = get_day_before_pretty(self.date_pretty)

            yesterday_analytics = ProductAnalytics.objects.get(
                product=self.product,
                date_pretty=yesterday_pretty,
            )
            return self.orders_amount - yesterday_analytics.orders_amount

        except Exception as e:
            return self.orders_amount

    def get_reviews_amount_in_day(self, date=None):
        """
        Get reviews amount in a day.
        Get yesterday's analytics and subtract today's reviews_amount from it.
        If there is no yesterday's analytics, return today's reviews_amount.
        """
        try:
            # get the latest analytics of this product
            yesterday_pretty = get_day_before_pretty(self.date_pretty)

            yesterday_analytics = ProductAnalytics.objects.get(
                product=self.product,
                date_pretty=yesterday_pretty,
            )
            return self.reviews_amount - yesterday_analytics.reviews_amount

        except Exception as e:
            return self.reviews_amount

    @staticmethod
    def update_average_purchase_price(date_pretty: str):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE product_productanalytics PA
                SET average_purchase_price = SA.avg_purchase_price
                FROM (
                    SELECT AVG(SA.purchase_price) as avg_purchase_price, S.product_id, SA.date_pretty
                    FROM sku_sku S
                    JOIN sku_skuanalytics SA ON S.sku = SA.sku_id
                    GROUP BY S.product_id, SA.date_pretty
                ) SA
                WHERE PA.product_id = SA.product_id AND PA.date_pretty = SA.date_pretty
                AND PA.date_pretty = %s
            """,
                [date_pretty],
            )

    @staticmethod
    def set_top_growing_products():
        # Set date range (last 30 days)
        end_date = pd.to_datetime(get_today_pretty()).tz_localize("UTC").astimezone(pytz.timezone("Asia/Tashkent"))
        start_date = end_date - pd.DateOffset(days=30)

        # Retrieve product sales data for the last 30 days
        sales_data = ProductAnalytics.objects.filter(created_at__range=[start_date, end_date]).values(
            "product__product_id", "date_pretty", "orders_amount"
        )

        # Convert QuerySet to DataFrame
        sales_df = pd.DataFrame.from_records(sales_data)

        # Make sure date_pretty is a datetime type
        sales_df["date_pretty"] = pd.to_datetime(sales_df["date_pretty"])

        # Set date_pretty as index (required for rolling function)
        sales_df = sales_df.set_index("date_pretty").sort_index()

        for span in [3, 5, 7, 30]:
            sales_df[f"ema_{span}_days"] = sales_df.groupby("product__product_id")["orders_amount"].transform(
                lambda x: x.ewm(span=span).mean()
            )

        sales_df["trend_3_to_7"] = sales_df["ema_3_days"] / sales_df["ema_7_days"]
        sales_df["trend_5_to_7"] = sales_df["ema_5_days"] / sales_df["ema_7_days"]
        sales_df["trend_3_to_30"] = sales_df["ema_3_days"] / sales_df["ema_30_days"]
        sales_df["trend_5_to_30"] = sales_df["ema_5_days"] / sales_df["ema_30_days"]

        # Reset index (to allow the next operations)
        sales_df = sales_df.reset_index()

        # Get the last day (most recent) of EMA ratio for each product
        sales_df = sales_df.groupby("product__product_id").last()

        # Only consider products with total sales greater than a certain threshold
        sales_df = sales_df[sales_df["orders_amount"] > 200]

        weights = [0.4, 0.3, 0.2, 0.1]  # adjust these weights as needed
        sales_df["score"] = sales_df[
            [
                "trend_3_to_7",
                "trend_5_to_7",
                "trend_3_to_30",
                "trend_5_to_30",
            ]
        ].apply(lambda x: np.average(x, weights=weights), axis=1)

        # Sort products by EMA ratio in descending order and take the top 100
        top_growing_products = sales_df.sort_values("score", ascending=False).head(100)

        # Return the list of top growing product IDs
        top_growing_products = top_growing_products.index.tolist()
        # set to cache with tieout 1 day
        print("setting top_growing_products to cache", len(top_growing_products), top_growing_products)
        cache.set("top_growing_products", top_growing_products, timeout=None)

    @staticmethod
    def set_orders_money(date_pretty: str):
        try:
            # Convert date_pretty to a timezone-aware datetime object
            date = timezone.make_aware(
                datetime.strptime(date_pretty, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            with connection.cursor() as cursor:
                if date_pretty == "2023-05-20":
                    # Handle the entries for date_pretty="2023-05-20" separately
                    cursor.execute(
                        """
                        WITH today_pa AS (
                            SELECT *
                            FROM product_productanalytics
                            WHERE date_pretty = %s AND average_purchase_price IS NOT NULL
                        )
                        UPDATE product_productanalytics
                        SET orders_money = (today_pa.orders_amount * today_pa.average_purchase_price) / 1000.0
                        FROM today_pa
                        WHERE product_productanalytics.product_id = today_pa.product_id
                        AND product_productanalytics.date_pretty = %s
                        """,
                        [date_pretty, date_pretty],
                    )
                else:
                    # Handle the entries for other dates
                    cursor.execute(
                        """
                        WITH today_pa AS (
                            SELECT *
                            FROM product_productanalytics
                            WHERE date_pretty = %s
                        ),
                        order_difference AS (
                            SELECT
                                today_pa.product_id,
                                (today_pa.orders_amount - COALESCE(latest_pa.latest_orders_amount, 0)) AS delta_orders,
                                COALESCE(latest_pa.latest_orders_money, 0) AS latest_orders_money
                            FROM
                                today_pa
                        LEFT JOIN product_latest_analytics latest_pa ON today_pa.product_id = latest_pa.product_id
                        ),
                        delta_orders_money AS (
                           SELECT
                                order_difference.product_id,
                                GREATEST(
                                    (order_difference.latest_orders_money + ((order_difference.delta_orders * today_pa.average_purchase_price) / 1000.0)),
                                    0
                                ) AS new_orders_money
                            FROM
                                order_difference
                                JOIN today_pa ON order_difference.product_id = today_pa.product_id
                            WHERE today_pa.average_purchase_price IS NOT NULL
                        )
                        UPDATE product_productanalytics
                        SET orders_money = delta_orders_money.new_orders_money
                        FROM delta_orders_money
                        WHERE product_productanalytics.product_id = delta_orders_money.product_id
                        AND product_productanalytics.date_pretty = %s
                        """,
                        [date_pretty, date_pretty],
                    )
        except Exception as e:
            print(e)

    @staticmethod
    def update_analytics(date_pretty: str):
        try:
            yesterday_pretty = get_day_before_pretty(date_pretty)
            create_product_latestanalytics(yesterday_pretty)
            ProductAnalytics.update_average_purchase_price(date_pretty)
            ProductAnalytics.set_orders_money(date_pretty)
            ProductAnalytics.set_positions(date_pretty)
            ProductAnalytics.set_top_growing_products()
        except Exception as e:
            print(e)
            traceback.print_exc()


class ProductAnalyticsView(models.Model):
    product_id = models.IntegerField(primary_key=True)
    product_title = models.CharField(max_length=255)
    product_title_ru = models.CharField(max_length=255, null=True, blank=True)
    product_characteristics = models.TextField(blank=True, null=True)
    orders_amount = models.IntegerField()
    product_available_amount = models.IntegerField()
    reviews_amount = models.IntegerField()
    rating = models.FloatField()
    shop_title = models.CharField(max_length=255)
    shop_link = models.TextField()
    category_id = models.IntegerField()
    photos = models.TextField(blank=True, null=True)
    date_pretty = models.CharField(max_length=255)
    position_in_category = models.IntegerField(blank=True, null=True)
    badges = models.TextField(blank=True, null=True)
    sku_analytics = models.TextField(blank=True, null=True)
    category_title = models.CharField(max_length=255)
    category_title_ru = models.CharField(max_length=255, null=True, blank=True)
    avg_purchase_price = models.FloatField(blank=True, null=True)
    orders_money = models.FloatField(blank=True, null=True, default=0.0)

    class Meta:
        managed = False
        db_table = "product_sku_analytics"


class LatestProductAnalyticsView(models.Model):
    product_id = models.IntegerField(primary_key=True)
    last_updated_at = models.DateTimeField()
    latest_orders_money = models.DecimalField(max_digits=10, decimal_places=2)
    latest_average_purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    latest_orders_amount = models.IntegerField()

    class Meta:
        managed = False
        db_table = "product_latest_analytics"


def create_product_latestanalytics(date_pretty: str):
    # Convert date_pretty to a timezone-aware datetime object
    date = (
        pytz.timezone("Asia/Tashkent")
        .localize(datetime.strptime(date_pretty, "%Y-%m-%d"))
        .replace(hour=23, minute=59, second=59, microsecond=999999)
    )

    with connection.cursor() as cursor:
        # Drop the materialized view if it exists
        cursor.execute("DROP MATERIALIZED VIEW IF EXISTS product_latest_analytics")

        # Create the materialized view
        cursor.execute(
            f"""
            CREATE MATERIALIZED VIEW product_latest_analytics AS
            SELECT DISTINCT ON (product_id) product_id, created_at as last_updated_at,
                orders_money as latest_orders_money,
                average_purchase_price as latest_average_purchase_price,
                orders_amount as latest_orders_amount
            FROM product_productanalytics
            WHERE created_at <= '{date}'
            ORDER BY product_id, created_at DESC
        """
        )
