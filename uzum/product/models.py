import uuid
from datetime import datetime

import pytz
from django.db import models
from django.db.models import F, Window, JSONField
from django.db.models.functions import Rank
from django.db import connection
from uzum.sku.models import get_day_before_pretty


class Product(models.Model):
    product_id = models.IntegerField(unique=True, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    title = models.TextField(db_index=True)
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


def get_today_pretty():
    return datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")


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
    orders_money = models.IntegerField(default=0)

    campaigns = models.ManyToManyField(
        "campaign.Campaign",
    )
    date_pretty = models.CharField(max_length=255, null=True, blank=True, db_index=True, default=get_today_pretty)
    position_in_shop = models.IntegerField(default=0, null=True, blank=True)
    position_in_category = models.IntegerField(default=0, null=True, blank=True)
    position = models.IntegerField(default=0, null=True, blank=True)

    @staticmethod
    def set_position_in_shop(date_pretty=get_today_pretty()):
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
                                ORDER BY pa.orders_amount DESC
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

                cursor.execute(
                    f"""
                    WITH ranked_products AS (
                        SELECT
                            pa.id,
                            RANK() OVER (
                                PARTITION BY p.category_id
                                ORDER BY pa.orders_amount DESC
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

                cursor.execute(
                    f"""
                    WITH ranked_products AS (
                        SELECT
                            pa.id,
                            RANK() OVER (
                                ORDER BY pa.orders_amount DESC
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


class ProductAnalyticsView(models.Model):
    product_id = models.IntegerField(primary_key=True)
    product_title = models.CharField(max_length=255)
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
    avg_purchase_price = models.FloatField(blank=True, null=True)

    class Meta:
        managed = False
        db_table = "product_sku_analytics"
