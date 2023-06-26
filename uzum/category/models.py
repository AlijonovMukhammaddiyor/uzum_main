import traceback
import uuid
from datetime import datetime, timedelta

import pytz
from django.db import models, transaction
from django.db.models import Avg, Count, F, Q, Subquery, Sum

from uzum.product.models import Product, ProductAnalytics, get_today_pretty
from uzum.shop.models import Shop
from uzum.sku.models import get_day_before_pretty


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

    total_orders = models.IntegerField(default=0, null=True, blank=True)  # total orders of campaign so far
    total_orders_amount = models.IntegerField(
        default=0, null=True, blank=True
    )  # total orders amount of campaign so far

    total_reviews = models.IntegerField(default=0, null=True, blank=True)  # so far
    average_rating = models.FloatField(default=0, null=True, blank=True)  # so far

    total_shops = models.IntegerField(default=0, null=True, blank=True)  # current

    total_shops_with_sales = models.IntegerField(default=0, null=True, blank=True)  # in a day
    total_products_with_sales = models.IntegerField(default=0, null=True, blank=True)  # in a day
    total_products_with_reviews = models.IntegerField(default=0, null=True, blank=True)  # in a day

    def __str__(self):
        return f"{self.category.categoryId}: {self.total_products}"

    def get_yesterday_category_analytics(self):
        """
        Returns last category analytics for this category with date it created.
        Args:
            date_prety (_type_, optional): _description_. Defaults to None.

        Returns:
            _type_: _description_
        """
        try:
            yesterday_pretty = get_day_before_pretty(self.date_pretty)
            last_analytics = CategoryAnalytics.objects.get(category=self.category, date_pretty=yesterday_pretty)
            return last_analytics
        except Exception as e:
            return None

    def set_total_shops(self, date=None):
        try:
            # 1. get all descendants of this category
            descendants = Category.get_descendants(self.category, include_self=True)

            # 1. get all products in descendants
            products = Product.objects.filter(category__in=descendants)

            # 2. traverse all products and increment count if shop is not already counted
            count = 0
            counted = {}

            for product in products:
                shop: Shop = product.shop
                if shop.seller_id not in counted:
                    count += 1
                    counted[shop.seller_id] = True

            self.total_shops = count
            self.save()

        except Exception as e:
            print("Error in set_total_shops: ", e)

    @staticmethod
    def update_all_categories(date_pretty=None):
        if date_pretty is None:
            date_pretty = datetime.now().strftime("%Y-%m-%d")

        current_date = datetime.strptime(date_pretty, "%Y-%m-%d").astimezone(pytz.timezone("Asia/Tashkent"))

        categories = Category.objects.all()

        updated_categories_analytics = []

        for category in categories:
            descendants = Category.get_descendants(category, include_self=True)

            products = Product.objects.filter(category__in=descendants)

            total_orders = 0
            total_reviews = 0
            product_with_sale_count = 0
            shop_with_sale_count = set()
            products_with_reviews_count = 0
            rating = 0
            rated_products_count = 0

            for product in products:
                product_analytic = (
                    ProductAnalytics.objects.filter(product=product, created_at__date__lte=current_date.date())
                    .order_by("-created_at")
                    .first()
                )

                if product_analytic is not None:
                    total_orders += product_analytic.orders_amount
                    total_reviews += product_analytic.reviews_amount

                    if product_analytic.orders_amount > 0:
                        product_with_sale_count += 1
                        shop_with_sale_count.add(product.shop.seller_id)

                    if product_analytic.reviews_amount > 0:
                        products_with_reviews_count += 1

                    if product_analytic.rating > 0:
                        rating += product_analytic.rating
                        rated_products_count += 1
            print(category.title)
            try:
                category_analytics = CategoryAnalytics.objects.get(category=category, date_pretty=date_pretty)
            except CategoryAnalytics.DoesNotExist:
                continue
            category_analytics.total_orders = total_orders
            category_analytics.total_reviews = total_reviews
            category_analytics.total_products_with_sales = product_with_sale_count
            category_analytics.total_shops_with_sales = len(shop_with_sale_count)
            category_analytics.total_products_with_reviews = products_with_reviews_count
            category_analytics.average_rating = (rating / rated_products_count) if rated_products_count > 0 else 0

            updated_categories_analytics.append(category_analytics)

        with transaction.atomic():
            CategoryAnalytics.objects.bulk_update(
                updated_categories_analytics,
                [
                    "total_orders",
                    "total_reviews",
                    "total_products_with_sales",
                    "total_shops_with_sales",
                    "total_products_with_reviews",
                    "average_rating",
                ],
            )
