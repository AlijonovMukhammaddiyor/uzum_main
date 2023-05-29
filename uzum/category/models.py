import uuid
from datetime import datetime, timedelta

from django.db import models

from uzum.product.models import Product, ProductAnalytics, get_today_pretty
from uzum.shop.models import Shop


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
    created_at = models.DateTimeField(auto_now_add=True)
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
        descendant_ids = self.descendants.split(",")

        # convert to int
        descendant_ids = [int(descendant_id) for descendant_id in descendant_ids]
        descendants = Category.objects.filter(id__in=descendant_ids)

        if include_self:
            descendants = descendants | Category.objects.filter(categoryId=self.categoryId)

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

    total_orders = models.IntegerField(default=0)  # total orders of campaign so far
    total_orders_amount = models.IntegerField(default=0)  # total orders amount of campaign so far

    total_reviews = models.IntegerField(default=0)
    average_rating = models.FloatField(default=0)

    total_shops = models.IntegerField(default=0)

    total_shops_with_sales = models.IntegerField(default=0)
    total_products_with_sales = models.IntegerField(default=0)

    def __str__(self):
        return f"{self.category.categoryId}: {self.total_products}"

    def get_last_category_analytics(self, date=None):
        """
        Returns last category analytics for this category with date it created.
        Args:
            date_prety (_type_, optional): _description_. Defaults to None.

        Returns:
            _type_: _description_
        """
        try:
            if not date:
                date = datetime.now()

            last_analytics = (
                CategoryAnalytics.objects.filter(category=self.category, created_at__lt=date)
                .order_by("-created_at")
                .first()
            )
            return last_analytics
        except Exception as e:
            print("Error in get_last_category_analytics: ", e)

    def set_total_products_with_sale(self, date=None):
        """
        Sets total_products_with_sales for this category.
        For efficience, set total_shops_with_sales as well.
        Args:
            date (_type_, optional): _description_. Defaults to None.
        """
        try:
            if not date:
                date = datetime.now()
            date_pretty = date.strftime("%Y-%m-%d")

            # get all product_analytics created at date_pretty for this category
            product_analytics = ProductAnalytics.objects.filter(
                product__category=self.category, date_pretty=date_pretty
            )

            # traverse all and if analytics.get_orders_amount_in_day(date) > 0, then increment count
            count = 0
            shops_counted = {}
            shop_count = 0
            for product_analytic in product_analytics:
                if product_analytic.get_orders_amount_in_day(date) > 0:
                    count += 1

                    shop: Shop = product_analytic.product.shop
                    if shop.seller_id not in shops_counted:
                        shops_counted[shop.seller_id] = True
                        shop_count += 1

            self.total_products_with_sales = count
            self.total_shops_with_sales = shop_count
            self.save()

        except Exception as e:
            print("Error in set_total_products_with_sale: ", e)

    def set_total_shops(self, date=None):
        try:
            # get all shops which have product in this category

            # 1. get all products in this category
            products = Product.objects.filter(category=self.category)

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

    def set_total_reviews(self, date=None):
        """
        Sets total_reviews for this category.
        Args:
            date (_type_, optional): _description_. Defaults to None.
        """
        try:
            # get all product_analytics created at date_pretty for this category
            # sum all reviews_amount
            if not date:
                date = datetime.now()
            date_pretty = date.strftime("%Y-%m-%d")

            product_analytics = ProductAnalytics.objects.filter(
                product__category=self.category, date_pretty=date_pretty
            )

            reviews = 0
            total_rating = 0
            rating_count = 0

            for product_analytic in product_analytics:
                reviews += product_analytic.reviews_amount
                total_rating += product_analytic.rating
                if product_analytic.rating > 0:
                    rating_count += 1

            if rating_count > 0:
                self.average_rating = total_rating / rating_count
            self.total_reviews = reviews
            self.save()

        except Exception as e:
            print("Error in set_total_reviews: ", e)

    def set_total_orders(self, date=None):
        """
        Sets total_orders for this category.
        Args:
            date (_type_, optional): _description_. Defaults to None.
        """
        try:
            # get all product_analytics created at date_pretty for this category
            # sum all orders_amount
            if not date:
                date = datetime.now()
            date_pretty = date.strftime("%Y-%m-%d")

            product_analytics = ProductAnalytics.objects.filter(
                product__category=self.category, date_pretty=date_pretty
            )

            orders = 0

            for product_analytic in product_analytics:
                orders += product_analytic.orders_amount

            self.total_orders = orders
            self.save()

            return True
        except Exception as e:
            print("Error in set_total_orders: ", e)
