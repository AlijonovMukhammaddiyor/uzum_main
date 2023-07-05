from collections import defaultdict
import uuid
from datetime import datetime, timedelta

import pytz
from django.db import models
from django.db.models import Window, F, Subquery, OuterRef, Count
from django.db.models.functions import Rank
from django.apps import apps

from uzum.product.models import Product


def get_today_pretty():
    return datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")


def get_model(app_name, model_name):
    return apps.get_model(app_name, model_name)


class Shop(models.Model):
    seller_id = models.IntegerField(primary_key=True)
    avatar = models.TextField(null=True, blank=True)
    banner = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    has_charity_products = models.BooleanField(default=False)
    link = models.TextField(null=True, blank=True)
    official = models.BooleanField(default=False)
    info = models.TextField(null=True, blank=True)  # json.dumps(info)
    registration_date = models.DateTimeField(null=True, blank=True)
    title = models.TextField(null=True, blank=True)
    account_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class ShopAnalytics(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="analytics")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    total_products = models.IntegerField(default=0)
    total_orders = models.IntegerField(default=0)
    total_reviews = models.IntegerField(default=0)
    average_purchase_price = models.FloatField(default=0, null=True, blank=True)
    average_order_price = models.FloatField(default=0, null=True, blank=True)
    rating = models.FloatField(default=0)
    banners = models.ManyToManyField(
        "banner.Banner",
    )
    date_pretty = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        default=get_today_pretty,
    )

    categories = models.ManyToManyField(
        "category.Category",
    )

    def __str__(self):
        return f"{self.shop.title} - {self.total_products}"

    @staticmethod
    def set_average_price(date_pretty: str = get_today_pretty()):
        from django.db import connection

        try:
            with connection.cursor() as cursor:
                # update average_price
                cursor.execute(
                    """
                    UPDATE shop_shopanalytics sa
                    SET average_purchase_price = (
                        SELECT AVG(ska.purchase_price)
                        FROM sku_skuanalytics ska
                        JOIN sku_sku s ON ska.sku_id = s.sku
                        JOIN product_product p ON s.product_id = p.product_id
                        WHERE sa.shop_id = p.shop_id AND sa.date_pretty = %s AND ska.date_pretty = %s
                    )
                    WHERE sa.date_pretty = %s
                    """,
                    [date_pretty, date_pretty, date_pretty],
                )
        except Exception as e:
            print("Error in set_average_price: ", e)

    @staticmethod
    def set_categories_and_total_products_for_date(date_pretty):
        # Get queryset of shops and annotate with total_products
        shop_products_subquery = Product.objects.filter(shop=OuterRef("pk")).order_by().values("shop")

        shop_products_subquery = shop_products_subquery.annotate(product_count=Count("product_id")).values(
            "product_count"
        )

        # Get queryset of shops and annotate with categories
        Category = get_model("category", "Category")

        shop_categories_subquery = (
            Category.objects.filter(products__shop=OuterRef("pk")).order_by().values("products__shop")
        )

        shop_categories_subquery = shop_categories_subquery.annotate(category_count=Count("categoryId")).values(
            "category_count"
        )

        # Update the ShopAnalytics model
        ShopAnalytics.objects.filter(date_pretty=date_pretty).update(
            total_products=Subquery(shop_products_subquery[:1]),
            categories=Subquery(shop_categories_subquery[:1]),
        )

    @staticmethod
    def set_total_products(date_pretty: str = get_today_pretty()):
        from django.db import connection

        try:
            with connection.cursor() as cursor:
                # update total_products
                cursor.execute(
                    """
                    UPDATE shop_shopanalytics sa
                    SET total_products = (
                        SELECT COUNT(*)
                        FROM product_productanalytics pa
                        JOIN product_product p ON pa.product_id = p.product_id
                        WHERE sa.shop_id = p.shop_id AND sa.date_pretty = %s AND pa.date_pretty = %s
                    )
                    WHERE sa.date_pretty = %s
                    """,
                    [date_pretty, date_pretty, date_pretty],
                )
        except Exception as e:
            print("Error in set_total_products: ", e)

    @staticmethod
    def set_categories(date_pretty: str = get_today_pretty()):
        from django.db import connection

        try:
            with connection.cursor() as cursor:
                # remove existing categories of the day
                cursor.execute(
                    """
                    DELETE FROM shop_shopanalytics_categories
                    WHERE shopanalytics_id IN (
                        SELECT id FROM shop_shopanalytics
                        WHERE date_pretty = %s
                    )
                """,
                    [date_pretty],
                )

                # insert categories
                cursor.execute(
                    """
                INSERT INTO shop_shopanalytics_categories(shopanalytics_id, category_id)
                SELECT sa.id, p.category_id
                FROM shop_shopanalytics sa
                JOIN product_product p ON sa.shop_id = p.shop_id
                JOIN product_productanalytics pa ON p.product_id = pa.product_id
                WHERE sa.date_pretty = %s AND pa.date_pretty = %s
                GROUP BY sa.id, p.category_id
                """,
                    [date_pretty, date_pretty],
                )
        except Exception as e:
            print("Error in set_categories: ", e)
