import gc
import traceback
import uuid
from datetime import datetime

import numpy as np
import pandas as pd
import pytz
from django.core.cache import cache
from django.db import connection, models

from uzum.utils.general import get_day_before_pretty, get_today_pretty


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
    # characteristics_ru = models.TextField(null=True, blank=True)  # json.dumps(characteristics_ru)

    def __str__(self) -> str:
        return f"{self.product_id} - {self.title}"


class ProductAnalytics(models.Model):
    class Meta:
        db_table = "product_productanalytics"

    # Identifiers
    id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        primary_key=True,
    )
    product = models.ForeignKey(Product, on_delete=models.DO_NOTHING, related_name="analytics")

    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    date_pretty = models.CharField(max_length=255, null=True, blank=True, default=get_today_pretty, db_index=True)

    # Relational Fields
    banners = models.ManyToManyField(
        "banner.Banner",
    )
    badges = models.ManyToManyField("badge.Badge", related_name="products")
    campaigns = models.ManyToManyField("campaign.Campaign")

    # Counts and Metrics
    available_amount = models.IntegerField(default=0, db_index=True)
    reviews_amount = models.IntegerField(default=0)
    rating = models.FloatField(default=0)
    orders_amount = models.IntegerField(default=0, db_index=True)  # number of orders so far
    real_orders_amount = models.IntegerField(
        default=0, null=True, blank=True, db_index=True
    )  # how many products actully deducted from the stock daily - one order can have multiple products
    daily_revenue = models.FloatField(
        default=0.0, null=True, blank=True
    )  # daily revenue amount from real_orders_amount
    orders_money = models.FloatField(default=0.0)  # total revenue amount from real_orders_amount

    # Positional and Pricing Data
    position_in_shop = models.IntegerField(default=0, null=True, blank=True)
    position_in_category = models.IntegerField(default=0, null=True, blank=True)
    position = models.IntegerField(default=0, null=True, blank=True)
    positions = models.TextField(null=True, blank=True)
    average_purchase_price = models.IntegerField(default=0, null=True, blank=True)

    # Miscellaneous
    score = models.FloatField(default=0, null=True, blank=True)

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
                    SELECT AVG(filtered_SA.purchase_price) as avg_purchase_price, S.product_id
                    FROM sku_sku S
                    JOIN (
                        SELECT *
                        FROM sku_skuanalytics
                        WHERE date_pretty = %s
                    ) AS filtered_SA ON S.sku = filtered_SA.sku_id
                    GROUP BY S.product_id
                ) SA
                WHERE PA.product_id = SA.product_id AND PA.date_pretty = %s
            """,
                [date_pretty, date_pretty],
            )

    @staticmethod
    def set_top_growing_products():
        gc.collect()
        # Set date range (last 30 days)
        end_date = pd.to_datetime(get_today_pretty()).tz_localize("UTC").astimezone(pytz.timezone("Asia/Tashkent"))
        start_date = end_date - pd.DateOffset(days=30)

        product_ids = ProductAnalytics.objects.filter(
            date_pretty=get_today_pretty(), orders_amount__gte=40
        ).values_list("product_id", flat=True)

        print("product_ids", len(product_ids))

        # Retrieve product sales data for the last 30 days
        sales_data = ProductAnalytics.objects.filter(
            created_at__range=[start_date, end_date], product_id__in=product_ids
        ).values("product__product_id", "date_pretty", "orders_amount")

        # Convert QuerySet to DataFrame
        sales_df = pd.DataFrame.from_records(sales_data)

        # Make sure date_pretty is a datetime type
        sales_df["date_pretty"] = pd.to_datetime(sales_df["date_pretty"])

        # Set date_pretty as index (required for rolling function)
        sales_df.set_index("date_pretty", inplace=True)
        sales_df.sort_index(inplace=True)

        # Calculate Exponential Moving Averages for the given spans
        for span in [3, 5, 7, 30]:
            sales_df[f"ema_{span}_days"] = sales_df.groupby("product__product_id")["orders_amount"].transform(
                lambda x: x.ewm(span=span).mean()
            )

        sales_df["trend_3_to_7"] = sales_df["ema_3_days"] / sales_df["ema_7_days"]
        sales_df["trend_5_to_7"] = sales_df["ema_5_days"] / sales_df["ema_7_days"]
        sales_df["trend_3_to_30"] = sales_df["ema_3_days"] / sales_df["ema_30_days"]
        sales_df["trend_5_to_30"] = sales_df["ema_5_days"] / sales_df["ema_30_days"]

        # Reset index (to allow the next operations)
        sales_df.reset_index(inplace=True)

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
        print("Starting to update top_growing_products")
        create_temp_table_sql = """
        CREATE TEMPORARY TABLE temp_scores (
            product_id INT PRIMARY KEY,
            date_pretty DATE,
            score FLOAT
        );
        """

        with connection.cursor() as cursor:
            cursor.execute(create_temp_table_sql)

        # Step 2: Insert Data into the Temporary Table
        # Convert your DataFrame's data into a list of tuples
        data_tuples = list(zip(sales_df.index, sales_df["date_pretty"], sales_df["score"]))
        print("data_tuples", len(data_tuples))

        # values = ', '.join(map(str, data_tuples))
        values = ", ".join(["(%s, %s, %s)"] * len(data_tuples))
        insert_sql = f"""
        INSERT INTO temp_scores (product_id, date_pretty, score) VALUES {values}
        """
        with connection.cursor() as cursor:
            cursor.execute(insert_sql, sum(data_tuples, ()))

            # Step 3: Update the Main Table using a JOIN
            cursor.execute(
                """
                    UPDATE product_productanalytics
                    SET score = temp_scores.score
                    FROM temp_scores
                    WHERE product_productanalytics.product_id = temp_scores.product_id AND product_productanalytics.date_pretty = temp_scores.date_pretty::text
                    """
            )

        # Step 4: Drop the Temporary Table (Optional but recommended)
        drop_temp_table_sql = "DROP TABLE temp_scores;"
        with connection.cursor() as cursor:
            cursor.execute(drop_temp_table_sql)

        # Return the list of top growing product IDs
        top_growing_products = top_growing_products.index.tolist()
        # set to cache with tieout 1 day
        print("setting top_growing_products to cache", len(top_growing_products), top_growing_products)
        cache.set("top_growing_products", top_growing_products, timeout=None)
        gc.collect()

    @staticmethod
    def update_analytics(date_pretty: str):
        try:
            ProductAnalytics.set_positions(date_pretty)
            ProductAnalytics.set_top_growing_products()
            ProductAnalytics.update_positions(date_pretty)
        except Exception as e:
            print(e)
            traceback.print_exc()

    @staticmethod
    def update_real_orders_amount(date_pretty: str):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE product_productanalytics pa
                    SET real_orders_amount =
                        CASE
                            WHEN (COALESCE(lpa.latest_available_amount, 0) - pa.available_amount) >= (pa.orders_amount - COALESCE(lpa.latest_orders_amount, 0))
                            THEN (COALESCE(lpa.latest_available_amount, 0) - pa.available_amount)
                            ELSE (pa.orders_amount - COALESCE(lpa.latest_orders_amount, 0))
                        END
                    FROM product_latest_analytics lpa
                    WHERE pa.product_id = lpa.product_id
                    AND pa.date_pretty = %s
                    """,
                    [date_pretty],
                )
        except Exception as e:
            print(e)

    # should be executed after sku analytics is done
    @staticmethod
    def set_daily_revenue(date_pretty: str):
        try:
            # get all sku analytics for the given date_pretty of the products
            # then sum up the orders_money of the sku analytics and set it to the daily_revenue of the product analytics
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH sku_product_totals AS (
                        -- Aggregate totals from sku_skuanalytics for each product
                        SELECT
                            sku.product_id,
                            SUM(sa.orders_money) as total_orders_money
                        FROM
                            sku_skuanalytics sa
                        JOIN
                            sku_sku sku ON sa.sku_id = sku.sku
                        WHERE
                            sa.date_pretty = %s
                        GROUP BY
                            sku.product_id
                    )

                    UPDATE
                        product_productanalytics ppa
                    SET
                        daily_revenue = spt.total_orders_money
                    FROM
                        sku_product_totals spt
                    WHERE
                        ppa.product_id = spt.product_id
                        AND ppa.date_pretty = %s;
                    """,
                    [date_pretty, date_pretty],
                )

        except Exception as e:
            print(e)

    @staticmethod
    def update_positions(date_pretty=get_today_pretty()):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH RECURSIVE ancestors_cte AS (
                        SELECT
                            c."categoryId",
                            c."title" AS category_title,
                            SPLIT_PART(SPLIT_PART(c.ancestors_ru, '/', n), ':', 1) AS ancestor_title,
                            CAST(SPLIT_PART(SPLIT_PART(c.ancestors_ru, '/', n), ':', 2) AS INTEGER) AS category_id
                        FROM
                            (SELECT "categoryId", "title", ancestors_ru, GENERATE_SERIES(1, COALESCE(ARRAY_LENGTH(REGEXP_SPLIT_TO_ARRAY(ancestors_ru, '/'), 1), 1)) AS n FROM category_category) c
                        WHERE
                            c.ancestors_ru IS NOT NULL AND
                            c.ancestors_ru != '' AND
                            c."categoryId" != 1 AND
                            LENGTH(c.ancestors_ru) - LENGTH(REPLACE(c.ancestors_ru, '/', '')) >= c.n - 1
                        UNION ALL
                        SELECT
                            c."categoryId",
                            c."title_ru" AS category_title,
                            c."title_ru" AS ancestor_title,
                            c."categoryId" AS category_id
                        FROM
                            category_category c
                ),
                product_ranks AS (
                    SELECT
                        pav.product_id,
                        anc.category_title,
                        anc.category_id,
                        anc."categoryId",
                        anc.ancestor_title,
                        RANK() OVER(PARTITION BY anc.category_id ORDER BY pav.monthly_revenue DESC) AS rank
                    FROM
                        product_sku_analytics pav
                    JOIN
                        ancestors_cte anc ON pav.category_id = anc."categoryId"
                    WHERE
                        anc.category_id IS NOT NULL  -- Ensure only non-NULL category_ids are considered
                )
                UPDATE
                    product_productanalytics pa
                SET
                    positions = ranks_concat
                FROM (
                    SELECT
                        pr.product_id,
                        pr."categoryId",
                        STRING_AGG(CONCAT(pr.ancestor_title, '#', pr.rank), ',') AS ranks_concat
                    FROM
                        product_ranks pr
                    GROUP BY
                        pr.product_id, pr."categoryId"
                ) pr
                WHERE
                    pa.product_id = pr.product_id AND pa.date_pretty = %s;

                    """,
                    [date_pretty],
                )

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
    diff_orders_amount = models.IntegerField(blank=True, null=True)
    diff_reviews_amount = models.IntegerField(blank=True, null=True)
    diff_orders_money = models.FloatField(blank=True, null=True)
    product_created_at = models.DateTimeField(blank=True, null=True)
    weekly_orders_money = models.FloatField(blank=True, null=True)
    weekly_orders_amount = models.IntegerField(blank=True, null=True)
    weekly_reviews_amount = models.IntegerField(blank=True, null=True)
    revenue_3_days = models.FloatField(blank=True, null=True)
    orders_3_days = models.IntegerField(blank=True, null=True)
    weekly_revenue = models.FloatField(blank=True, null=True)
    weekly_orders = models.IntegerField(blank=True, null=True)
    monthly_revenue = models.FloatField(blank=True, null=True)
    monthly_orders = models.IntegerField(blank=True, null=True)
    revenue_90_days = models.FloatField(blank=True, null=True)
    orders_90_days = models.IntegerField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "product_sku_analytics"


class LatestProductAnalyticsView(models.Model):
    product_id = models.IntegerField(primary_key=True)
    last_updated_at = models.DateTimeField()
    latest_orders_money = models.DecimalField(max_digits=10, decimal_places=2)
    latest_average_purchase_price = models.DecimalField(max_digits=10, decimal_places=2)
    latest_orders_amount = models.IntegerField()
    latest_available_amount = models.IntegerField()

    class Meta:
        managed = False
        db_table = "product_latest_analytics"


def create_product_latestanalytics(date_pretty: str):
    # Convert date_pretty to a timezone-aware datetime object
    date = (
        pytz.timezone("Asia/Tashkent")
        .localize(datetime.strptime(date_pretty, "%Y-%m-%d"))
        .replace(hour=20, minute=59, second=59, microsecond=999999)
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
                orders_amount as latest_orders_amount,
                available_amount as latest_available_amount
            FROM product_productanalytics
            WHERE created_at <= '{date}'
            ORDER BY product_id, created_at DESC
        """
        )
