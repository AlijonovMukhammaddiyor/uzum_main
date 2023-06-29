import traceback
import uuid
from datetime import datetime, timedelta

import pytz
from django.db import models, transaction
from django.db.models import Avg, Subquery, Sum, OuterRef

from uzum.product.models import Product, ProductAnalytics, get_today_pretty
from uzum.shop.models import Shop
from uzum.sku.models import SkuAnalytics, get_day_before_pretty


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
    def set_all_analytics(date_pretty=get_today_pretty()):
        try:
            # Fetch CategoryAnalytics objects for the specific date
            category_analytics_on_date = CategoryAnalytics.objects.filter(date_pretty=date_pretty)

            with transaction.atomic():
                for category_analytics in category_analytics_on_date:
                    category = category_analytics.category
                    descendants = Category.get_descendants(category, include_self=True)

                    # Get the latest ProductAnalytics for each product in the category
                    latest_product_analytics = ProductAnalytics.objects.filter(
                        product__category__in=descendants,
                        created_at=Subquery(
                            ProductAnalytics.objects.filter(product=OuterRef("product"))
                            .order_by("-created_at")
                            .values("created_at")[:1]
                        ),
                    )

                    # Get the latest SkuAnalytics for each product in the category
                    latest_sku_analytics = SkuAnalytics.objects.filter(
                        sku__product__category__in=descendants,
                        created_at=Subquery(
                            SkuAnalytics.objects.filter(sku=OuterRef("sku"))
                            .order_by("-created_at")
                            .values("created_at")[:1]
                        ),
                    )

                    # Calculate totals and averages
                    total_orders = latest_product_analytics.aggregate(sum=Sum("orders_amount"))["sum"] or 0
                    total_reviews = latest_product_analytics.aggregate(sum=Sum("reviews_amount"))["sum"] or 0
                    average_product_rating = latest_product_analytics.aggregate(avg=Avg("rating"))["avg"] or 0

                    # Calculate total_shops
                    total_shops = Shop.objects.filter(products__category__in=descendants).distinct().count()

                    # Get yesterday's analytics for comparison
                    last_analytics = category_analytics.get_yesterday_category_analytics()

                    if last_analytics:
                        # Calculate total_shops_with_sales
                        total_shops_with_sales = (
                            Shop.objects.filter(
                                products__category__in=descendants,
                                products__productanalytics__orders_amount__gt=last_analytics.total_orders,
                            )
                            .distinct()
                            .count()
                        )

                        # Calculate total_products_with_sales
                        total_products_with_sales = (
                            Product.objects.filter(
                                category__in=descendants,
                                productanalytics__orders_amount__gt=last_analytics.total_orders,
                            )
                            .distinct()
                            .count()
                        )
                    else:
                        total_shops_with_sales = total_shops
                        total_products_with_sales = category_analytics.total_products

                    # Calculate average_purchase_price
                    total_purchase_price = latest_sku_analytics.aggregate(sum=Sum("purchase_price"))["sum"] or 0
                    total_number_of_skus = latest_sku_analytics.count()
                    average_purchase_price = total_purchase_price / total_number_of_skus if total_number_of_skus else 0

                    # Update CategoryAnalytics
                    category_analytics.total_orders = total_orders
                    category_analytics.total_reviews = total_reviews
                    category_analytics.average_product_rating = average_product_rating
                    category_analytics.total_shops = total_shops
                    category_analytics.total_shops_with_sales = total_shops_with_sales
                    category_analytics.total_products_with_sales = total_products_with_sales
                    category_analytics.average_purchase_price = average_purchase_price
                    category_analytics.save()

        except Exception as e:
            traceback.print_exc()
            print("Error in set_all_analytics: ", e)

    @staticmethod
    def update_total_shops_for_date(date_pretty=get_today_pretty()):
        try:
            categories = Category.objects.all()

            with transaction.atomic():
                for category in categories:
                    descendants = Category.get_descendants(category, include_self=True)

                    shop_count = Product.objects.filter(category__in=descendants).values("shop").distinct().count()

                    CategoryAnalytics.objects.filter(category=category, date_pretty=date_pretty).update(
                        total_shops=shop_count
                    )

        except Exception as e:
            traceback.print_exc()
            print("Error in set_total_shops: ", e)
