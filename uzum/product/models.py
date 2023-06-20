import uuid
from datetime import datetime

import pytz
from django.db import models

from uzum.sku.models import get_day_before_pretty


class Product(models.Model):
    product_id = models.IntegerField(unique=True, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    title = models.TextField()
    description = models.TextField(default=None, null=True, blank=True)
    adult = models.BooleanField(default=False, db_index=True)
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
    product = models.ForeignKey(Product, on_delete=models.DO_NOTHING, related_name="analytics")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    banners = models.ManyToManyField("banner.Banner", db_index=True)
    badges = models.ManyToManyField(
        "badge.Badge",
        db_index=True,
        related_name="products",
    )

    available_amount = models.IntegerField(default=0)
    reviews_amount = models.IntegerField(default=0)
    rating = models.FloatField(default=0)
    orders_amount = models.IntegerField(default=0)
    orders_money = models.IntegerField(default=0)

    campaigns = models.ManyToManyField(
        "campaign.Campaign",
        db_index=True,
    )
    date_pretty = models.CharField(max_length=255, null=True, blank=True, db_index=True, default=get_today_pretty)
    position = models.IntegerField(default=0, null=True, blank=True)
    score = models.FloatField(default=0, null=True, blank=True)

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

    # def set_orders_money(self):
    #     """
    #     Set orders money.
    #     Get all corresponding skuAnalytics and sum their purchase_price.
    #     """
    #     try:
    #         sku_analytics = SkuAnalytics.objects.filter(sku__product=self.product, date_pretty=self.date_pretty)
    #         orders_money = 0

    #         # check if every sku has 0 orders_amount

    #         for sku_analytic in sku_analytics:
    #             orders_money += sku_analytic.purchase_price * sku_analytic.orders_amount

    #         self.orders_money = orders_money
    #         self.save()
    #         return True
    #     except Exception as e:
    #         print("Error in set_orders_money: ", e)
    #         return None
