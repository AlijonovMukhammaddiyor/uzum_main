import uuid
from datetime import datetime

import numpy as np
import pandas as pd
import pytz
from django.core.cache import cache
from django.db import connection, models
from django.utils import timezone

from uzum.utils.general import get_day_before_pretty, get_today_pretty


class Category(models.Model):
    categoryId = models.IntegerField(unique=True, null=False, blank=False, primary_key=True)
    title = models.CharField(max_length=1024)
    seo = models.TextField(blank=True, null=True)
    adult = models.BooleanField(default=False, db_index=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        related_name="child_categories",
        null=True,
    )
    children = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="parent_cats")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    descendants = models.TextField(null=True, blank=True)  # descendant categoryIds separated by comma
    ancestors = models.TextField(null=True, blank=True)

    def generate_ancestors_string(self):
        current_category = self
        ancestors = []

        while current_category.parent:
            ancestors.append(current_category.parent.title + ":" + str(current_category.parent.categoryId))
            current_category = current_category.parent

        # reverse the list since we want to start from the root
        ancestors.reverse()

        # join the list using '/' as a delimiter
        return "/".join(ancestors)

    @staticmethod
    def update_ancestors():
        """
        Updates ancestors field of all categories.
        """
        i = 0
        categories = Category.objects.all()
        for category in categories:
            print(i)
            i += 1
            ancestors = category.generate_ancestors_string()
            category.ancestors = ancestors
            category.save()

    def __str__(self):
        return self.title + " " + str(self.categoryId)

    @staticmethod
    def update_descendants():
        """
        Updates descendants field of all categories.
        """
        categories = Category.objects.all()
        for category in categories:
            descendants = Category.get_descendants(category)
            if len(descendants) > 0:
                descendants = [str(descendant.categoryId) for descendant in descendants]
                descendants = ",".join(descendants)
                category.descendants = descendants
                category.save()

    @staticmethod
    def get_descendants(category, include_self=False):
        descendants = []

        # Recursive function to retrieve descendants
        def retrieve_descendants(category):
            children = category.children.all()
            for child in children:
                descendants.append(child)
                retrieve_descendants(child)

        retrieve_descendants(category)

        if include_self:
            descendants.append(category)

        return descendants

    def get_category_descendants(self, include_self=False):
        if self.descendants is None:
            if include_self:
                return [self]
            else:
                return []
        descendant_ids = [int(descendant_id) for descendant_id in self.descendants.split(",")]

        if include_self:
            descendant_ids.append(self.categoryId)

        descendants = Category.objects.filter(categoryId__in=descendant_ids)

        return descendants


class CategoryAnalytics(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    category = models.ForeignKey(
        Category,
        on_delete=models.DO_NOTHING,
    )

    total_products = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    date_pretty = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        default=get_today_pretty,
    )

    total_orders = models.IntegerField(null=True, blank=True)  # total orders of category so far
    total_orders_amount = models.IntegerField(null=True, blank=True)  # total orders amount of category so far

    total_reviews = models.IntegerField(null=True, blank=True)  # so far
    average_product_rating = models.FloatField(null=True, blank=True)  # so far

    total_shops = models.IntegerField(null=True, blank=True)  # current

    total_shops_with_sales = models.IntegerField(null=True, blank=True)  # between yesterday and today
    total_products_with_sales = models.IntegerField(null=True, blank=True)  # between yesterday and today

    average_purchase_price = models.FloatField(null=True, blank=True)  # average price of all products in category
    average_order_price = models.FloatField(
        null=True, blank=True
    )  # average price of all orders in category between yesterday and today

    def __str__(self):
        return f"{self.category.categoryId}: {self.total_products}"

    def get_yesterday_category_analytics(self):
        """
        Returns yesterday's category analytics if exists, else None
        Args:
            date_prety (_type_, optional): _description_. Defaults to None.

        Returns:
            _type_: _description_
        """
        try:
            yesterday_pretty = get_day_before_pretty(self.date_pretty)
            last_analytics = CategoryAnalytics.objects.get(category=self.category, date_pretty=yesterday_pretty)
            return last_analytics
        except CategoryAnalytics.DoesNotExist:
            return None
        except Exception as e:
            print("Error in get_yesterday_category_analytics: ", e)
            return None

    @staticmethod
    def set_average_purchase_price(date_pretty=None):
        try:
            if date_pretty is None:
                date_pretty = get_today_pretty()

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH agg_price AS (
                        SELECT
                            c."categoryId",
                            AVG(pa.average_purchase_price) as average_price
                        FROM
                            category_category c
                            INNER JOIN product_product p ON p.category_id = ANY(
                                ARRAY[c."categoryId"] || CASE WHEN c.descendants IS NOT NULL THEN string_to_array(c.descendants, ',')::integer[] ELSE ARRAY[]::integer[] END
                            )
                            INNER JOIN product_productanalytics pa ON pa.product_id = p.product_id AND pa.date_pretty = %s
                        GROUP BY
                            c."categoryId"
                    )
                    UPDATE
                        category_categoryanalytics cca
                    SET
                        average_purchase_price = agg_price.average_price
                    FROM
                        agg_price
                    WHERE
                        cca.category_id = agg_price."categoryId"
                        AND cca.date_pretty = %s
                    """,
                    [date_pretty, date_pretty],
                )
        except Exception as e:
            print(e, "Error in set_average_purchase_price")

    @staticmethod
    def update_totals_for_date(date_pretty):
        try:
            # Convert date_pretty to datetime
            date = timezone.make_aware(
                datetime.strptime(date_pretty, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=23, minute=59, second=0, microsecond=0)

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH latest_pa AS (
                    SELECT DISTINCT ON (pa.product_id) pa.product_id, pa.orders_amount, pa.reviews_amount, pa.rating
                    FROM product_productanalytics pa
                    WHERE pa.created_at <= %s
                    ORDER BY pa.product_id, pa.created_at DESC
                ),
                aggs AS (
                    SELECT
                        c."categoryId" AS categoryid,
                        COALESCE(SUM(lpa.orders_amount), 0) as total_orders,
                        COALESCE(SUM(lpa.reviews_amount), 0) as total_reviews,
                        COALESCE(AVG(NULLIF(lpa.rating, 0)), 0) as average_rating
                    FROM
                        category_category c
                        LEFT JOIN product_product p ON p.category_id = ANY(
                            ARRAY[c."categoryId"] || CASE WHEN c.descendants IS NOT NULL THEN string_to_array(c.descendants, ',')::integer[] ELSE ARRAY[]::integer[] END
                        )
                        LEFT JOIN latest_pa lpa ON lpa.product_id = p.product_id
                    GROUP BY
                        c."categoryId"
                )
                UPDATE
                    category_categoryanalytics cca
                SET
                    total_orders = aggs.total_orders,
                    total_reviews = aggs.total_reviews,
                    average_product_rating = aggs.average_rating
                FROM
                    aggs
                WHERE
                    cca.category_id = aggs.categoryid
                    AND cca.date_pretty = %s
                    """,
                    [date, date_pretty],
                )
        except Exception as e:
            print("Error in update_totals_for_date: ", e)

    @staticmethod
    def update_totals_for_shops_and_products(date_pretty=None):
        try:
            if date_pretty is None:
                date_pretty = get_today_pretty()

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH category_totals AS (
                        SELECT
                            c."categoryId",
                            COUNT(DISTINCT p.shop_id) as total_shops,
                            COUNT(pa.product_id) as total_products
                        FROM
                            category_category c
                            INNER JOIN product_productanalytics pa ON pa.date_pretty = %s
                            INNER JOIN product_product p ON pa.product_id = p.product_id AND p.category_id = ANY(
                                CASE
                                    WHEN c.descendants IS NULL THEN ARRAY[c."categoryId"]::integer[]
                                    ELSE ARRAY[c."categoryId"] || string_to_array(c.descendants, ',')::integer[]
                                END
                            )
                        GROUP BY
                            c."categoryId"
                    )
                    UPDATE
                        category_categoryanalytics ca
                    SET
                        total_shops = ct.total_shops,
                        total_products = ct.total_products
                    FROM
                        category_totals ct
                    WHERE
                        ca.category_id = ct."categoryId" AND ca.date_pretty = %s
                    """,
                    [date_pretty, date_pretty],
                )
        except Exception as e:
            print(e, "Error in update_totals_for_shops_and_products")

    @staticmethod
    def update_totals_with_sale(date_pretty=get_today_pretty()):
        try:
            # Convert the date_pretty to a datetime object and set it to be timezone aware
            date = timezone.make_aware(
                datetime.strptime(date_pretty, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH latest_pa AS (
                        SELECT DISTINCT ON (product_id) *
                        FROM product_productanalytics
                        WHERE created_at < %s
                        ORDER BY product_id, created_at DESC
                    ),
                    today_pa AS (
                        SELECT *
                        FROM product_productanalytics
                        WHERE date_pretty = %s
                    ),
                    order_difference AS (
                        SELECT
                            today_pa.product_id,
                            product_product.shop_id,
                            (today_pa.orders_amount - COALESCE(latest_pa.orders_amount, 0)) AS difference
                        FROM
                            today_pa
                            JOIN product_product ON today_pa.product_id = product_product.product_id
                            LEFT JOIN latest_pa ON today_pa.product_id = latest_pa.product_id
                    ),
                    shops_and_products_with_sales AS (
                        SELECT
                            category_category."categoryId",
                            COUNT(DISTINCT order_difference.shop_id) FILTER (WHERE order_difference.difference > 0) AS total_shops_with_sales,
                            COUNT(DISTINCT order_difference.product_id) FILTER (WHERE order_difference.difference > 0) AS total_products_with_sales
                        FROM
                            category_category
                            LEFT JOIN product_product ON product_product.category_id = ANY (
                                CASE
                                    WHEN category_category.descendants IS NULL THEN ARRAY[category_category."categoryId"]::integer[]
                                    ELSE ARRAY[category_category."categoryId"] || string_to_array(category_category.descendants, ',')::integer[]
                                END
                            )
                            LEFT JOIN order_difference ON order_difference.product_id = product_product.product_id
                        GROUP BY
                            category_category."categoryId"
                    )
                    UPDATE
                        category_categoryanalytics
                    SET
                        total_shops_with_sales = shops_and_products_with_sales.total_shops_with_sales,
                        total_products_with_sales = shops_and_products_with_sales.total_products_with_sales
                    FROM
                        shops_and_products_with_sales
                    WHERE
                        category_categoryanalytics.category_id = shops_and_products_with_sales."categoryId"
                        AND category_categoryanalytics.date_pretty = %s
                    """,
                    [date, date_pretty, date_pretty],
                )
        except Exception as e:
            print(e, "Error in update_totals_with_sale")

    @staticmethod
    def update_analytics(date_pretty=get_today_pretty()):
        try:
            CategoryAnalytics.update_totals_for_date(date_pretty)
            CategoryAnalytics.update_totals_for_shops_and_products(date_pretty)
            CategoryAnalytics.update_totals_with_sale(date_pretty)
            CategoryAnalytics.set_average_purchase_price(date_pretty)
        except Exception as e:
            print(e, "Error in update_analytics")

    @staticmethod
    def set_top_growing_categories_ema():
        # Set date range (last 50 days)
        end_date = pd.to_datetime("2023-07-13")
        start_date = end_date - pd.DateOffset(days=50)

        # Retrieve category sales data for the last 50 days
        sales_data = CategoryAnalytics.objects.filter(
            created_at__range=[start_date, end_date], category__descendants=None
        ).values("category__categoryId", "created_at", "total_orders")

        # Convert QuerySet to DataFrame
        sales_df = pd.DataFrame.from_records(sales_data)

        # Make sure created_at is a datetime type
        sales_df["created_at"] = pd.to_datetime(sales_df["created_at"])

        # Set created_at as index (required for rolling function)
        sales_df = sales_df.set_index("created_at").sort_index()

        # Group by category and calculate the 3-day, 7-day, 14-day, 21-day, 30-day, and 50-day EMA of sales
        for span in [3, 7, 14, 21, 30, 50]:
            sales_df[f"ema_{span}_days"] = sales_df.groupby("category__categoryId")["total_orders"].transform(
                lambda x: x.ewm(span=span).mean()
            )

        # Calculate trend indicators (ratios of EMAs)
        sales_df["trend_3_to_7"] = sales_df["ema_3_days"] / sales_df["ema_7_days"]
        sales_df["trend_7_to_14"] = sales_df["ema_7_days"] / sales_df["ema_14_days"]
        sales_df["trend_7_to_21"] = sales_df["ema_7_days"] / sales_df["ema_21_days"]
        sales_df["trend_14_to_30"] = sales_df["ema_14_days"] / sales_df["ema_30_days"]
        sales_df["trend_21_to_50"] = sales_df["ema_21_days"] / sales_df["ema_50_days"]

        # Reset index (to allow the next operations)
        sales_df = sales_df.reset_index()

        # Get the last day (most recent) of trend indicators for each category
        sales_df = sales_df.groupby("category__categoryId").last()

        # Only consider categories with total orders greater than 100
        sales_df = sales_df[sales_df["total_orders"] > 100]

        # Calculate score as the mean of trend indicators
        weights = [0.4, 0.3, 0.2, 0.1, 0.05]  # adjust these weights as needed
        sales_df["score"] = sales_df[
            [
                "trend_3_to_7",
                "trend_7_to_14",
                "trend_7_to_21",
                "trend_14_to_30",
                "trend_21_to_50",
            ]
        ].apply(lambda x: np.average(x, weights=weights), axis=1)

        # Sort categories by score in descending order and take the top 10
        top_growing_categories = sales_df.sort_values("score", ascending=False).head(20)

        # Return the list of top growing category IDs
        top_growing_categories = top_growing_categories.index.tolist()

        # Set to cache with timeout 1 day
        print("Setting top_growing_categories to cache", len(top_growing_categories), top_growing_categories)
        cache.set("top_growing_categories", top_growing_categories, timeout=60 * 60 * 24)
