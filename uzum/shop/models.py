import uuid
from datetime import datetime, timedelta

import pytz
from django.db import models
from django.db.models import F, Max, Window
from django.db.models.functions import DenseRank

from uzum.product.models import ProductAnalytics


def get_today_pretty():
    return datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")


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
        # db_index=True,
    )
    score = models.FloatField(default=0, null=True, blank=True)
    daily_position = models.IntegerField(default=0, null=True, blank=True)
    weekly_score = models.FloatField(default=0, null=True, blank=True)
    weekly_position = models.IntegerField(default=0, null=True, blank=True)
    monthly_score = models.FloatField(default=0, null=True, blank=True)
    monthly_position = models.IntegerField(default=0, null=True, blank=True)

    def __str__(self):
        return f"{self.shop.title} - {self.total_products}"

    def set_total_products(self):
        try:
            # get all product analytics of this shop
            product_analytics = ProductAnalytics.objects.filter(product__shop=self.shop, date_pretty=self.date_pretty)
            self.total_products = product_analytics.count()
            self.save()
        except Exception as e:
            print("Error in set_total_products: ", e)

    def set_categories(self):
        try:
            # get all products of the shop
            products = self.shop.products.all()

            categories = set()
            for product in products:
                # get all categories of the product
                categories.add(product.category)

            # set categories
            self.categories.set(categories)

        except Exception as e:
            print("Error in set_categories: ", e)

    @staticmethod
    def set_positions(date_pretty=get_today_pretty()):
        try:
            # Get all ShopAnalytics objects for the given date
            analytics_objects = ShopAnalytics.objects.filter(date_pretty=date_pretty)

            # get the max total_orders, rating and total_reviews across all ShopAnalytics
            max_total_orders = analytics_objects.aggregate(Max("total_orders"))["total_orders__max"]
            max_rating = analytics_objects.aggregate(Max("rating"))["rating__max"]
            max_total_reviews = analytics_objects.aggregate(Max("total_reviews"))["total_reviews__max"]
            max_total_products = analytics_objects.aggregate(Max("total_products"))["total_products__max"]

            growth_rates = []

            for analytics in analytics_objects:
                # normalize the values
                normalized_orders = analytics.total_orders / max_total_orders
                normalized_rating = analytics.rating / max_rating
                normalized_reviews = analytics.total_reviews / max_total_reviews
                normalized_products = analytics.total_products / max_total_products

                # calculate the growth_rate
                # first get the analytics object from previous day
                previous_day_analytics = ShopAnalytics.objects.filter(
                    shop=analytics.shop, date_pretty=(analytics.created_at - timedelta(days=1)).strftime("%Y-%m-%d")
                ).first()

                # If there is no previous day analytics (which means the shop is new)
                if previous_day_analytics:
                    growth_rate = (
                        (analytics.total_orders - previous_day_analytics.total_orders)
                        / previous_day_analytics.total_orders
                        if previous_day_analytics.total_orders != 0
                        else 0
                    )
                else:
                    # we can set the growth rate to 0 if there is no orders yet, otherwise 1
                    growth_rate = 0 if analytics.total_orders == 0 else 1

                # calculate the score using your weights
                score = (
                    0.65 * normalized_orders
                    + 0.1 * normalized_rating
                    + 0.2 * normalized_reviews
                    + 0.1 * normalized_products
                )

                growth_rates.append(growth_rate)

                analytics.score = score
                analytics.save()

            max_growth_rate = max(growth_rates) if growth_rates else 1

            for i, analytics in enumerate(analytics_objects):
                # normalize the growth rate
                normalized_growth_rate = growth_rates[i] / max_growth_rate if max_growth_rate else 0

                # add the impact of the growth rate to the score
                analytics.score += 0.2 * normalized_growth_rate
                analytics.save()

            # Rank the analytics objects based on the score and set the position
            ranked_analytics = sorted(analytics_objects, key=lambda a: a.score, reverse=True)
            for i, analytics in enumerate(ranked_analytics, start=1):
                analytics.daily_position = i
                analytics.save()

        except Exception as e:
            print("Error in set_position: ", e)
