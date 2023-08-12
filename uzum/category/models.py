import uuid
from collections import defaultdict
from datetime import datetime

import numpy as np
import pandas as pd
import pytz
from django.core.cache import cache
from django.db import connection, models
from django.utils import timezone
from statsmodels.nonparametric.smoothers_lowess import lowess

from uzum.utils.general import get_day_before_pretty, get_today_pretty


class Category(models.Model):
    categoryId = models.IntegerField(unique=True, null=False, blank=False, primary_key=True)
    title = models.CharField(max_length=1024)
    title_ru = models.CharField(max_length=1024, null=True, blank=True)
    seo = models.TextField(blank=True, null=True)
    adult = models.BooleanField(default=False, db_index=True)
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        blank=True,
        related_name="child_categories",
        null=True,
    )
    # children = models.ManyToManyField("self", blank=True, symmetrical=False, related_name="parent_cats")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)

    descendants = models.TextField(null=True, blank=True)  # descendant categoryIds separated by comma
    ancestors = models.TextField(null=True, blank=True)
    ancestors_ru = models.TextField(null=True, blank=True)  # new field for Russian ancestors

    def generate_ancestors_string(self, language="en"):
        current_category = self
        ancestors = []

        while current_category.parent:
            if language == "ru":
                ancestors.append(current_category.parent.title_ru + ":" + str(current_category.parent.categoryId))
            else:
                ancestors.append(current_category.parent.title + ":" + str(current_category.parent.categoryId))
            current_category = current_category.parent

        # reverse the list since we want to start from the root
        ancestors.reverse()

        # join the list using '/' as a delimiter
        return "/".join(ancestors)

    @staticmethod
    def update_ancestors():
        """
        Updates ancestors and ancestors_ru field of all categories.
        """
        i = 0
        categories = Category.objects.filter(
            models.Q(ancestors="") | models.Q(ancestors_ru="") | models.Q(ancestors=None)
        )
        print("Total categories: ", len(categories))
        for category in categories:
            print(i)
            i += 1
            ancestors = category.generate_ancestors_string()
            ancestors_ru = category.generate_ancestors_string("ru")  # generate Russian ancestors
            category.ancestors = ancestors
            category.ancestors_ru = ancestors_ru  # update Russian ancestors
            category.save()

    def __str__(self):
        return self.title + " " + str(self.categoryId)

    def update_descendants_rec(category, visited=None):
        if visited is None:
            visited = set()

        descendants = []

        def gather_descendants(cat):
            if cat in visited:
                print(f"Cycle detected at category id {cat.categoryId}")
                return
            visited.add(cat)

            if not cat.child_categories.all():
                return

            for child in cat.child_categories.all():
                if child == category:
                    print(f"Category {category.categoryId} is its own descendant!")
                    continue
                descendants.append(str(child.categoryId))
                gather_descendants(child)

        gather_descendants(category)
        category.descendants = ",".join(descendants)
        category.save()

    # def update_descendants():
    #     """
    #     Updates descendants field of all categories.
    #     """
    #     # select categories only if it has analytics at today
    #     categories = Category.objects.filter(categoryanalytics__date_pretty=get_today_pretty()).prefetch_related(
    #         "child_categories"
    #     )
    #     print("Total categories: ", len(categories))
    #     i = 0
    #     for category in categories:
    #         print(i)
    #         i += 1
    #         Category.update_descendants_rec(category)

    #     return None

    def update_descendants_bulk():
        #     categories = list(
        #         Category.objects.filter(categoryanalytics__date_pretty=get_today_pretty()).prefetch_related(
        #             "child_categories"
        #         )
        #     )
        #     print("Total categories: ", len(categories))

        #     for category in categories:
        #         descendants = []
        #         visited = set()
        #         stack = list(category.child_categories.all())

        #         while stack:
        #             current = stack.pop()
        #             if current in visited:
        #                 continue
        #             visited.add(current)
        #             descendants.append(str(current.categoryId))
        #             stack.extend(current.child_categories.all())

        #         category.descendants = ",".join(descendants)

        #     Category.objects.bulk_update(categories, ["descendants"])
        pass

    def get_category_descendants(self, include_self=False):
        if not self.descendants:
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

    total_orders = models.IntegerField(null=True, blank=True, default=0)  # total orders of category so far
    total_orders_amount = models.FloatField(
        null=True, blank=True, default=0.0
    )  # total orders amount of category so far

    total_reviews = models.IntegerField(null=True, blank=True, default=0)  # so far
    average_product_rating = models.FloatField(null=True, blank=True, default=0.0)  # so far

    total_shops = models.IntegerField(null=True, blank=True, default=0)  # current

    total_shops_with_sales = models.IntegerField(null=True, blank=True, default=0)  # between yesterday and today
    total_products_with_sales = models.IntegerField(null=True, blank=True, default=0)  # between yesterday and today

    average_purchase_price = models.FloatField(
        null=True, blank=True, default=0
    )  # average price of all products in category
    average_order_price = models.FloatField(
        null=True, blank=True, default=0
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
                    SELECT DISTINCT ON (pa.product_id) pa.product_id, pa.orders_amount, pa.reviews_amount, pa.rating, pa.orders_money
                    FROM product_productanalytics pa
                    WHERE pa.created_at <= %s
                    ORDER BY pa.product_id, pa.created_at DESC
                ),
                aggs AS (
                    SELECT
                        c."categoryId" AS categoryid,
                        COALESCE(SUM(lpa.orders_amount), 0) as total_orders,
                        COALESCE(SUM(lpa.reviews_amount), 0) as total_reviews,
                        COALESCE(AVG(NULLIF(lpa.rating, 0)), 0) as average_rating,
                        COALESCE(SUM(lpa.orders_money), 0) as total_orders_amount
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
                    average_product_rating = aggs.average_rating,
                    total_orders_amount = aggs.total_orders_amount
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
                             ARRAY[c."categoryId"] || CASE WHEN c.descendants IS NOT NULL THEN string_to_array(c.descendants, ',')::integer[] ELSE ARRAY[]::integer[] END
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
                                ARRAY[category_category."categoryId"] || CASE WHEN category_category.descendants IS NOT NULL THEN string_to_array(category_category.descendants, ',')::integer[] ELSE ARRAY[]::integer[] END
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
            CategoryAnalytics.set_average_purchase_price(date_pretty)
            CategoryAnalytics.update_totals_for_shops_and_products(date_pretty)
            CategoryAnalytics.update_totals_for_date(date_pretty)
            CategoryAnalytics.update_totals_with_sale(date_pretty)
            CategoryAnalytics.set_top_growing_categories()
        except Exception as e:
            print(e, "Error in update_analytics")

    @staticmethod
    def set_top_growing_categories():
        # Helper function to calculate growth rate using linear regression
        def calculate_growth_rate(metric, smoothing_window=7):
            daily_metrics = defaultdict(list)

            analytics_data = (
                CategoryAnalytics.objects.filter(category__child_categories__isnull=True)
                .values("category", "created_at", metric)
                .order_by("category", "created_at")
            )

            print("Length of analytics_data: ", len(analytics_data))
            previous_entry = None

            for entry in analytics_data:
                if previous_entry and entry["category"] == previous_entry["category"]:
                    daily_revenue = entry[metric] - previous_entry[metric]
                    daily_metrics[entry["category"]].append((entry["created_at"], daily_revenue))
                else:
                    daily_metrics[entry["category"]].append((entry["created_at"], entry[metric]))
                previous_entry = entry

            # Smooth the data using LOESS
            smoothed_metrics = defaultdict(list)
            for category, data in daily_metrics.items():
                dates, revenues = zip(*data)

                # Handle potential NaN or infinite values
                revenues = np.nan_to_num(revenues)  # Convert NaN to 0 and inf to a large finite number

                # If revenue contains zeros, replace with a small positive value
                revenues = [r if r != 0 else 1e-5 for r in revenues]  # replace 0 with a small positive value

                smoothed_revenues = lowess(revenues, range(len(revenues)), frac=0.25)[
                    :, 1
                ]  # frac determines smoothing degree
                smoothed_metrics[category] = list(zip(dates, smoothed_revenues))

            # Compute Growth Rate
            growth_rates = {}
            for category, data in smoothed_metrics.items():
                dates, revenues = zip(*data[-30:])  # Only consider the last 30 days
                dates = [d.toordinal() for d in dates]

                # Check if there's enough variability in revenue
                if len(set(revenues)) > 1:
                    coefficients = np.polyfit(dates, revenues, 1)
                    slope = coefficients[0]
                    growth_rates[category] = slope

            # Sort categories by growth rate to get the top growing categories
            top_growing_categories = sorted(growth_rates.keys(), key=lambda x: growth_rates[x], reverse=True)[:20]
            return top_growing_categories

        # Calculate top growing categories for each metric
        # top_categories_by_product_count = calculate_growth_rate("total_products")
        top_categories_by_revenue = calculate_growth_rate("total_orders_amount")
        top_categories_by_orders = calculate_growth_rate("total_orders")
        print(
            "Setting top_growing_categories to cache",
            # len(top_categories_by_product_count),
            len(top_categories_by_revenue),
            len(top_categories_by_orders),
        )
        # cache.set("top_growing_categories", top_growing_categories, timeout=60 * 60 * 24)
        # cache.set("top_categories_by_product_count", top_categories_by_product_count, timeout=60 * 60 * 48)
        cache.set("top_categories_by_revenue", top_categories_by_revenue, timeout=60 * 60 * 48)
        cache.set("top_categories_by_orders", top_categories_by_orders, timeout=60 * 60 * 48)
