import math
import time
import traceback
from datetime import date, datetime, timedelta
from itertools import groupby

import numpy as np
import pandas as pd
import pytz
from django.core.cache import cache
from django.db import connection, transaction
from django.db.models import Avg, Case, Count, F, FloatField, OuterRef, Q, Subquery, Sum, When
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination, LimitOffsetPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from uzum.category.pagination import CategoryProductsPagination
from uzum.category.utils import calculate_shop_analytics_in_category
from uzum.product.models import Product, ProductAnalytics, ProductAnalyticsView
from uzum.review.views import CookieJWTAuthentication
from uzum.sku.models import SkuAnalytics
from uzum.users.models import User
from uzum.utils.general import (
    Tariffs,
    authorize_Base_tariff,
    authorize_Seller_tariff,
    get_days_based_on_tariff,
    get_today_pretty_fake,
)

from .models import Category, CategoryAnalytics
from .serializers import CategoryAnalyticsSeralizer, CategorySerializer, ProductAnalyticsViewSerializer


# Base tariff
class CurrentCategoryView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]

    @extend_schema(tags=["Category"])
    def get(self, request: Request, category_id: int):
        try:
            authorize_Base_tariff(request)

            category = get_object_or_404(Category, pk=category_id)
            if not category:
                return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})

            serializer = CategorySerializer(category)
            return Response(status=status.HTTP_200_OK, data=serializer.data)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Free tariff
class AllCategoriesSegmentation(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategoryAnalyticsSeralizer

    def get(self, request: Request):
        try:
            # pass
            # get all category analytics with date_pretty = today which do not have children

            data = {
                "revenue": cache.get("category_tree_revenue"),
                "orders": cache.get("category_tree_orders"),
                "products": cache.get("category_tree_products"),
                "reviews": cache.get("category_tree_reviews"),
                "shops": cache.get("category_tree_shops"),
            }

            return Response(status=status.HTTP_200_OK, data=data)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class CategoryTreeView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]

    @staticmethod
    def get_category_tree(category: Category):
        categories = Category.objects.values("categoryId", "title", "parent_id")

        # first create a dictionary mapping ids to category data
        category_dict = {category["categoryId"]: category for category in categories}

        # then build a mapping from parent_id to a list of its children
        children_map = {}
        for category in categories:
            children_map.setdefault(category["parent_id"], []).append(category)

        # recursive function to build the tree
        def build_tree(category_id):
            category = category_dict[category_id]
            children = children_map.get(category_id, [])
            return {
                "categoryId": category_id,
                "title": category["title"],
                "children": [build_tree(child["categoryId"]) for child in children],
            }

        # build the tree starting from the root
        category_tree = build_tree(1)
        # store in cache
        cache.set("category_tree", category_tree, timeout=60 * 60 * 48)  # 48 hours
        return category_tree

    @extend_schema(tags=["Category"])
    def get(self, request: Request):
        try:
            authorize_Base_tariff(request)
            redis_key = "category_tree"

            if cache.get(redis_key):
                return Response(status=status.HTTP_200_OK, data=cache.get("category_tree"))
            print("category tree not found")
            root_category = Category.objects.get(categoryId=1)
            category_tree = self.get_category_tree(root_category)
            cache.set(redis_key, category_tree, timeout=60 * 60 * 24)
            print("category tree done")
            return Response(status=status.HTTP_200_OK, data=category_tree)

        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})

        except Exception as e:
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CategoriesToExcelView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Category"])
    def get(self, request: Request):
        try:
            authorize_Base_tariff(request)
            date_pretty = get_today_pretty_fake()
            # get all categoryanalytics with date_pretty
            categories = (
                CategoryAnalytics.objects.filter(date_pretty=date_pretty)
                .values(
                    "total_orders",
                    "total_reviews",
                    "total_products",
                    "total_shops",
                    "total_orders_amount",
                    "average_purchase_price",
                    "average_product_rating",
                    "category__title_ru",
                    "category__title",
                )
                .exclude(category__categoryId=1)
                .order_by("-total_orders_amount")
            )

            return Response(status=status.HTTP_200_OK, data=categories)

        except Exception as e:
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class CategoryProductsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ProductAnalyticsViewSerializer
    pagination_class = LimitOffsetPagination
    VALID_SEARCHES = ["shop_title", "product_title", "category_title"]

    def get_queryset(self):
        """
        This view should return a list of all the products for
        the category as determined by the category portion of the URL.
        """
        category_id = self.kwargs["category_id"]
        category = get_object_or_404(Category, pk=category_id)
        # Get the descendant category IDs as a list of integers
        if not category.descendants:
            descendant_ids = []
        else:
            descendant_ids = list(map(int, category.descendants.split(",")))

        descendant_ids.append(category_id)
        params = self.request.GET

        # Dictionary to hold the actual ORM filters
        orm_filters = {}
        instant_filter = params.get("instant_filter", None)  # can be revenue, monthly_revenue, created_at

        # Extracting sorting parameters
        column = params.get("column", "orders_money")  # Get the column to sort by
        order = params.get("order", "desc")  # Get the order (asc/desc)
        categories = descendant_ids

        if not categories:
            # return empty queryset
            return ProductAnalyticsView.objects.none()

        if not instant_filter:
            for key, value in params.items():
                if key in ["column", "order", "categories"]:
                    continue  # Skip sorting parameters

                if "__range" in key:
                    # Splitting the values and converting to numbers
                    min_val, max_val = map(int, value.strip("[]").split(","))
                    orm_filters[key] = (min_val, max_val)
                elif "__gte" in key or "__lte" in key:
                    orm_filters[key] = int(value)
                elif "__icontains" in key:
                    orm_filters[key] = value

                if key.startswith("orders_money") or key.startswith("diff_orders_money"):
                    # divide by 1000
                    values = orm_filters[key]
                    if values and isinstance(values, list):
                        orm_filters[key] = [int(value) / 1000.0 for value in values]
                    elif values:
                        orm_filters[key] = int(value) / 1000.0

                if key.startswith("product_created_at"):
                    # Convert the timestamp back to a datetime object with the correct timezone
                    values = orm_filters.get(key)
                    # check if values is list
                    if values and isinstance(values, list):
                        orm_filters[key] = [
                            datetime.fromtimestamp(int(values[0]) / 1000.0, tz=pytz.timezone("Asia/Tashkent")).replace(
                                hour=0, minute=0, second=0, microsecond=0
                            ),
                            datetime.fromtimestamp(int(values[1]) / 1000.0, tz=pytz.timezone("Asia/Tashkent")).replace(
                                hour=23, minute=59, second=59, microsecond=999999
                            ),
                        ]
                    elif values and key.endswith("gte"):
                        orm_filters[key] = datetime.fromtimestamp(
                            int(value) / 1000.0, tz=pytz.timezone("Asia/Tashkent")
                        ).replace(hour=0, minute=0, second=0, microsecond=0)
                    elif values and key.endswith("lte"):
                        orm_filters[key] = datetime.fromtimestamp(
                            int(value) / 1000.0, tz=pytz.timezone("Asia/Tashkent")
                        ).replace(hour=23, minute=59, second=59, microsecond=999999)

        print(orm_filters)
        order_prefix = "-" if order == "desc" else ""
        # # Now, use the orm_filters to query the database
        if not instant_filter:
            queryset = ProductAnalyticsView.objects.filter(**orm_filters, category_id__in=categories)
        if instant_filter == "revenue":
            queryset = ProductAnalyticsView.objects.filter(category_id__in=categories).order_by(
                "-orders_money", order_prefix + column
            )[:100]
        if instant_filter == "monthly_revenue":
            queryset = ProductAnalyticsView.objects.filter(category_id__in=categories).order_by(
                "-diff_orders_money", order_prefix + column
            )[:100]
        if instant_filter == "created_at":
            queryset = ProductAnalyticsView.objects.filter(category_id__in=categories).order_by(
                "-product_created_at", order_prefix + column
            )[:100]

        if column and not instant_filter:
            order_prefix = "-" if order == "desc" else ""  # Add "-" prefix for descending order
            queryset = queryset.order_by(order_prefix + column)

        return queryset

    def list(self, request, *args, **kwargs):
        start_time = time.time()

        authorize_Base_tariff(request)

        print("CATEGORY PRODUCTS")
        response = super().list(request, *args, **kwargs)
        print(f"CATEGORY PRODUCTS: {time.time() - start_time} seconds")
        return response


# Base tariff
class CategoryTopProductsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ProductAnalyticsViewSerializer
    pagination_class = CategoryProductsPagination
    allowed_methods = ["GET"]

    def get_products(self, category_id):
        """
        This view should return a list of all the products for
        the category as determined by the category portion of the URL.
        """
        # Get the category
        category = get_object_or_404(Category, pk=category_id)
        # Get the descendant category IDs as a list of integers
        if not category.descendants:
            descendant_ids = []
        else:
            descendant_ids = list(map(int, category.descendants.split(",")))

        descendants = category.get_category_descendants(include_self=True)

        # Add the parent category ID to the list
        descendant_ids.append(category_id)

        ca = CategoryAnalytics.objects.filter(category=category, date_pretty=get_today_pretty_fake()).first()

        if ca is None:
            total_orders = 0
            total_revenue = 0
            total_products = 0
        else:
            total_orders = ca.total_orders
            total_revenue = ca.total_orders_amount
            total_products = ca.total_products

        descendants_count = CategoryAnalytics.objects.filter(
            category__in=descendants, date_pretty=get_today_pretty_fake()
        ).count()

        # return ProductAnalyticsView.objects.filter(category_id__in=descendant_ids).order_by("-orders_amount")[:5]
        return {
            "products": ProductAnalyticsView.objects.filter(category_id__in=descendant_ids)
            .order_by("-orders_money")[:200]
            .values("product_id", "product_title", "product_title_ru", "orders_money"),
            "total_orders": total_orders,
            "total_revenue": total_revenue,
            "descendants": descendants_count - 1,
            "total_products": total_products,
        }

    def get(self, request, category_id: int):
        authorize_Base_tariff(request)
        products = self.get_products(category_id)
        return Response(status=status.HTTP_200_OK, data=products)


# Base tariff
class CategoryProductsPeriodComparisonView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @staticmethod
    @extend_schema(tags=["Category"])
    def get_category_products_comparison(category: Category):
        try:
            one_week_ago_date = timezone.now() - timedelta(weeks=1)
            two_weeks_ago_date = timezone.now() - timedelta(weeks=2)
            three_weeks_ago_date = timezone.now() - timedelta(weeks=3)
            four_weeks_ago_date = timezone.now() - timedelta(weeks=4)
            four_weeks_and_day_ago_date = timezone.now() - timedelta(weeks=4, days=1)

            date_pretty = get_today_pretty_fake()

            today_analytics = ProductAnalytics.objects.filter(product=OuterRef("pk"), date_pretty=date_pretty)
            week_ago_analytics = ProductAnalytics.objects.filter(
                product=OuterRef("pk"), date_pretty=one_week_ago_date.strftime("%Y-%m-%d")
            )
            two_weeks_ago_analytics = ProductAnalytics.objects.filter(
                product=OuterRef("pk"), date_pretty=two_weeks_ago_date.strftime("%Y-%m-%d")
            )
            three_weeks_ago_analytics = ProductAnalytics.objects.filter(
                product=OuterRef("pk"), date_pretty=three_weeks_ago_date.strftime("%Y-%m-%d")
            )
            four_weeks_ago_analytics = ProductAnalytics.objects.filter(
                product=OuterRef("pk"), date_pretty=four_weeks_ago_date.strftime("%Y-%m-%d")
            )
            four_weeks_and_day_ago_analytics = ProductAnalytics.objects.filter(
                product=OuterRef("pk"), date_pretty=four_weeks_and_day_ago_date.strftime("%Y-%m-%d")
            )

            today_sku_analytics = SkuAnalytics.objects.filter(
                sku__product_id=OuterRef("product_id"), date_pretty=date_pretty
            )
            week_ago_sku_analytics = SkuAnalytics.objects.filter(
                sku__product_id=OuterRef("product_id"), date_pretty=one_week_ago_date.strftime("%Y-%m-%d")
            )
            two_weeks_ago_sku_analytics = SkuAnalytics.objects.filter(
                sku__product_id=OuterRef("product_id"), date_pretty=two_weeks_ago_date.strftime("%Y-%m-%d")
            )
            three_weeks_ago_sku_analytics = SkuAnalytics.objects.filter(
                sku__product_id=OuterRef("product_id"), date_pretty=three_weeks_ago_date.strftime("%Y-%m-%d")
            )
            four_weeks_ago_sku_analytics = SkuAnalytics.objects.filter(
                sku__product_id=OuterRef("product_id"), date_pretty=four_weeks_ago_date.strftime("%Y-%m-%d")
            )
            four_weeks_and_day_ago_sku_analytics = SkuAnalytics.objects.filter(
                sku__product_id=OuterRef("product_id"), date_pretty=four_weeks_and_day_ago_date.strftime("%Y-%m-%d")
            )

            categories = category.get_category_descendants(include_self=True)

            category_products = (
                Product.objects.filter(category__in=categories)
                .annotate(
                    today_orders_amount=Subquery(today_analytics.values("orders_amount")[:1]),
                    week_ago_orders_amount=Subquery(week_ago_analytics.values("orders_amount")[:1]),
                    two_weeks_ago_orders_amount=Subquery(two_weeks_ago_analytics.values("orders_amount")[:1]),
                    three_weeks_ago_orders_amount=Subquery(three_weeks_ago_analytics.values("orders_amount")[:1]),
                    four_weeks_ago_orders_amount=Subquery(four_weeks_ago_analytics.values("orders_amount")[:1]),
                    four_weeks_and_day_ago_orders_amount=Subquery(
                        four_weeks_and_day_ago_analytics.values("orders_amount")[:1]
                    ),
                    today_reviews_amount=Subquery(today_analytics.values("reviews_amount")[:1]),
                    week_ago_reviews_amount=Subquery(week_ago_analytics.values("reviews_amount")[:1]),
                    two_weeks_ago_reviews_amount=Subquery(two_weeks_ago_analytics.values("reviews_amount")[:1]),
                    three_weeks_ago_reviews_amount=Subquery(three_weeks_ago_analytics.values("reviews_amount")[:1]),
                    four_weeks_ago_reviews_amount=Subquery(four_weeks_ago_analytics.values("reviews_amount")[:1]),
                    four_weeks_and_day_ago_reviews_amount=Subquery(
                        four_weeks_and_day_ago_analytics.values("reviews_amount")[:1]
                    ),
                    today_purchase_price=Subquery(today_sku_analytics.values("purchase_price")[:1]),
                    week_ago_purchase_price=Subquery(week_ago_sku_analytics.values("purchase_price")[:1]),
                    two_weeks_ago_purchase_price=Subquery(two_weeks_ago_sku_analytics.values("purchase_price")[:1]),
                    three_weeks_ago_purchase_price=Subquery(
                        three_weeks_ago_sku_analytics.values("purchase_price")[:1]
                    ),
                    four_weeks_ago_purchase_price=Subquery(four_weeks_ago_sku_analytics.values("purchase_price")[:1]),
                    four_weeks_and_day_ago_purchase_price=Subquery(
                        four_weeks_and_day_ago_sku_analytics.values("purchase_price")[:1]
                    ),
                )
                .values(
                    "title",
                    "description",
                    "shop__title",
                    "characteristics",
                    "photos",
                    "product_id",
                    "created_at",
                    "today_orders_amount",
                    "week_ago_orders_amount",
                    "two_weeks_ago_orders_amount",
                    "three_weeks_ago_orders_amount",
                    "four_weeks_ago_orders_amount",
                    "four_weeks_and_day_ago_orders_amount",
                    "today_reviews_amount",
                    "week_ago_reviews_amount",
                    "two_weeks_ago_reviews_amount",
                    "three_weeks_ago_reviews_amount",
                    "four_weeks_ago_reviews_amount",
                    "four_weeks_and_day_ago_reviews_amount",
                    "today_purchase_price",
                    "week_ago_purchase_price",
                    "two_weeks_ago_purchase_price",
                    "three_weeks_ago_purchase_price",
                    "four_weeks_ago_purchase_price",
                    "four_weeks_and_day_ago_purchase_price",
                )
                .order_by("-today_orders_amount")
            )

            return category_products

        except Exception as e:
            print(e)
            traceback.print_exc()
            return []

    @extend_schema(tags=["Category"])
    def get(self, request: Request, category_id):
        """
        Get products of a category.
        Args:
            request (Request): request should contain limit and offset query parameters.
            category_id (_type_): category id
            limit -> number of products to return
            offset -> offset of products to return
        Returns:
            _type_: _description_
        """
        try:
            authorize_Base_tariff(request)
            category = Category.objects.get(categoryId=category_id)
            category_products = self.get_category_products_comparison(category)

            paginator = self.pagination_class()  # new lines

            page = paginator.paginate_queryset(category_products, request)
            if page is not None:
                return paginator.get_paginated_response(page)

            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": category_products,
                    "total": len(category_products),
                },
            )

        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class CategoryDailyAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategoryAnalyticsSeralizer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @staticmethod
    def analytics(category: Category, start_date: datetime):
        try:
            end_date = timezone.make_aware(datetime.now(), timezone=pytz.timezone("Asia/Tashkent")).replace(
                hour=23, minute=59, second=59, microsecond=0
            )

            # if it is before 7 am in Tashkent, set end_date to 23:59 of the previous day
            if datetime.now(tz=pytz.timezone("Asia/Tashkent")).hour < 7:
                end_date = end_date - timedelta(days=1)

            category_analytics = CategoryAnalytics.objects.filter(
                category=category, created_at__range=[start_date, end_date]
            ).order_by("created_at")

            return CategoryAnalyticsSeralizer(category_analytics, many=True).data

        except Exception as e:
            print(e)
            traceback.print_exc()
            return []

    @extend_schema(tags=["Category"])
    def get(self, request: Request, category_id):
        """
        Get analytics of a category.
        Args:
            request (Request): request should contain page
            category_id (_type_): category id
            limit -> number of products to return
            offset -> offset of products to return
        Returns:
            [{
                "date_pretty": "2021-01-01",
                "orders_amount": 10,
                "total_products": 10,
                "total_review": 10,
                "total_shops_with_sales": 10,
                "total_shops": 10,
                "average_purchase_price": 10.0,
                "average_product_rating":  5
                "total_products_with_sales": 10,
            }]
        """
        try:
            authorize_Base_tariff(request)

            days = get_days_based_on_tariff(request.user)
            start = time.time()
            # get start_date 00:00 in Asia/Tashkent timezone which is range days ago
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=days + 1), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            category = Category.objects.get(categoryId=category_id)
            category_analytics = self.analytics(category, start_date)
            print(f"Category analytics: {time.time() - start} seconds")
            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": category_analytics,
                    "labels": [item["date_pretty"] for item in category_analytics],
                    "total": len(category_analytics),
                },
            )

        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class SubcategoriesView(APIView):
    """
    This class implements CategoryAnalytics for each subcategory.
    Args:
        APIView (_type_): _description_
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategoryAnalyticsSeralizer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @extend_schema(tags=["Category"])
    def get(self, request: Request, category_id):
        try:
            start = time.time()
            authorize_Base_tariff(request)
            category = Category.objects.get(categoryId=category_id)
            children = category.child_categories.all()

            if not children:
                return Response(status=status.HTTP_200_OK, data={"data": [], "total": 0, "main": []})

            date_pretty = get_today_pretty_fake()

            # Get main_analytics using raw SQL
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ca.*, c.title AS category_title, c.title_ru AS category_title_ru
                    FROM category_categoryanalytics AS ca
                    JOIN category_category AS c ON ca.category_id = c."categoryId"
                    WHERE ca.category_id = %s AND ca.date_pretty = %s
                """,
                    [category_id, date_pretty],
                )
                main_analytics = dictfetchall(cursor)

            # Get children_analytics using raw SQL
            ids = [child.categoryId for child in children]
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT ca.*, c.title AS category_title, c.title_ru AS category_title_ru
                    FROM category_categoryanalytics AS ca
                    JOIN category_category AS c ON ca.category_id = c."categoryId"
                    WHERE ca.category_id IN %s AND ca.date_pretty = %s
                """,
                    [tuple(ids), date_pretty],
                )
                children_analytics = dictfetchall(cursor)

            # for each category: title += "((category_id))"
            for child in children_analytics:
                child["category_title"] += f"(({child['category_id']}))"
                child["category_title_ru"] = (
                    child["category_title_ru"] if child["category_title_ru"] else child["category_title"]
                ) + f"(({child['category_id']}))"

            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": children_analytics,
                    "total": len(children_analytics),
                    "main": main_analytics,
                },
            )
        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


def dictfetchall(cursor):
    "Return all rows from a cursor as a dict"
    columns = [col[0] for col in cursor.description]
    return [dict(zip(columns, row)) for row in cursor.fetchall()]


# Base tariff
class CategoryPriceSegmentationView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @staticmethod
    def calculate_segment(segment_min_price, segment_max_price, products):
        segment_products = products.filter(avg_purchase_price__range=(segment_min_price, segment_max_price))

        segment_analytics = segment_products.aggregate(
            total_products=Count("product_id", distinct=True),
            total_shops=Count("shop_link", distinct=True),
            total_orders=Sum("orders_amount"),
            total_reviews=Sum("reviews_amount"),
            total_revenue=Sum("orders_money"),
            average_rating=Avg("rating"),
            avg_purchase_price=Avg("avg_purchase_price"),
        )

        return {
            "from": segment_min_price,
            "to": segment_max_price,
            **segment_analytics,
        }

    @extend_schema(tags=["Category"])
    def get(self, request: Request, category_id):
        try:
            start_time = time.time()
            authorize_Base_tariff(request)
            # range_count = request.query_params.get("range", 15)
            segments_count = request.query_params.get("segments_count", 15)

            segments_count = int(segments_count)

            # start_date = timezone.make_aware(
            #     datetime.now() - timedelta(days=int(range_count) + 1), timezone=pytz.timezone("Asia/Tashkent")
            # ).replace(hour=0, minute=0, second=0, microsecond=0)

            category = Category.objects.get(categoryId=category_id)
            if not category.descendants:
                descendant_ids = []
            else:
                descendant_ids = list(map(int, category.descendants.split(",")))

            # Add the parent category ID to the list
            descendant_ids.append(category_id)

            products = ProductAnalyticsView.objects.filter(category_id__in=descendant_ids)
            df = pd.DataFrame(list(products.values("product_id", "avg_purchase_price")))

            # Calculate the number of distinct average purchase prices
            distinct_prices_count = df["avg_purchase_price"].nunique()

            # Set the segments_count to the number of distinct prices if it exceeds the count
            segments_count = min(segments_count, distinct_prices_count)

            # Calculate the number of products per segment
            products_per_segment = len(df) // segments_count

            # Sort the DataFrame by average purchase price
            df = df.sort_values("avg_purchase_price")

            # Create the bins by dividing the DataFrame into segments with equal number of products
            bins = []
            start_idx = 0
            for i in range(segments_count):
                end_idx = start_idx + products_per_segment
                if i < len(df) % segments_count:
                    end_idx += 1
                min_price = df.iloc[start_idx]["avg_purchase_price"]
                max_price = df.iloc[end_idx - 1]["avg_purchase_price"]
                bins.append((min_price, max_price))
                start_idx = end_idx

            # Round the bin values to the nearest 1000
            bins = [
                (np.floor(min_price / 1000) * 1000, np.ceil(max_price / 1000) * 1000) for min_price, max_price in bins
            ]

            segments = []
            # with ThreadPoolExecutor(max_workers=segments_count) as executor:
            #     futures = []
            #     for i in range(len(bins)):
            #         (segment_min_price, segment_max_price) = bins[i]
            #         futures.append(
            #             executor.submit(
            #                 self.calculate_segment,
            #                 segment_min_price,
            #                 segment_max_price,
            #                 # start_date,
            #                 products,
            #             )
            #         )

            #     for future in as_completed(futures):
            #         segments.append(future.result())

            # without threads
            for i in range(len(bins)):
                (segment_min_price, segment_max_price) = bins[i]
                segments.append(
                    self.calculate_segment(
                        segment_min_price,
                        segment_max_price,
                        # start_date,
                        products,
                    )
                )

            print(f"Category Segmentation took {time.time() - start_time} seconds")
            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": segments,
                },
            )
        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class CategoryShopsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @staticmethod
    @transaction.atomic
    def shops_share(category: Category, start_date: datetime, end_date: datetime):
        # average_price_per_order = get_average_price_per_order(category, start_date, end_date)
        shop_shares = calculate_shop_analytics_in_category(
            category,
            start_date,
            end_date,
        )
        return shop_shares

    @extend_schema(tags=["Category"])
    def get(self, request: Request, category_id):
        try:
            start_time = time.time()
            authorize_Base_tariff(request)
            category = Category.objects.get(categoryId=category_id)

            if category.descendants:
                descendant_ids = list(map(int, category.descendants.split(",")))
            else:
                descendant_ids = []

            # Add the parent category ID to the list
            descendant_ids.append(category_id)
            shops = (
                ProductAnalyticsView.objects.filter(category_id__in=descendant_ids)
                .values("shop_link", "shop_title")  # group by shop_link and shop_title
                .annotate(
                    total_orders=Sum("orders_amount"),
                    total_products=Count("product_id", distinct=True),
                    total_reviews=Sum("reviews_amount"),
                    total_revenue=Sum("orders_money"),
                    average_product_rating=Avg(
                        Case(
                            When(rating__gt=0, then=F("rating")),  # only consider rating when it's greater than 0
                            default=None,
                            output_field=FloatField(),
                        )
                    ),
                    avg_purchase_price=Avg("avg_purchase_price"),
                )
            )

            data = list(shops)
            # convert title to title + ((shop_link))
            for item in data:
                item["title"] = f"{item['shop_title']} (({item['shop_link']}))"
                del item["shop_title"]
                del item["shop_link"]

            print(f"Category Shops took {time.time() - start_time} seconds")
            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": data,
                },
            )

        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class NicheSelectionView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    def get(self, request: Request):
        """
        Based on category analytics, returns the list of categories that are suitable for the niche
        Args:
            request (_type_): _description_

        Returns:
            _type_: _description_
        """
        try:
            start = time.time()
            authorize_Base_tariff(request)

            search = request.query_params.get("search", "")
            today_pretty = get_today_pretty_fake()

            categories = CategoryAnalytics.objects.filter(
                Q(category__ancestors__icontains=search) | Q(category__title__icontains=search),
                date_pretty=today_pretty,
                category__child_categories__isnull=True,
            ).values(
                "category__categoryId",
                "category__title",
                "category__title_ru",
                "category__ancestors",
                "category__ancestors_ru",
                "date_pretty",
                "total_products",
                "total_orders",
                "total_reviews",
                "total_shops",
                "total_shops_with_sales",
                "total_products_with_sales",
                "average_purchase_price",
                "average_product_rating",
                "total_orders_amount",
            )

            for category in categories:
                if category["category__categoryId"] != 1 and category["category__ancestors_ru"]:
                    category["category__ancestors_ru"] = (
                        category["category__ancestors_ru"]
                        if category["category__ancestors_ru"]
                        else category["category__ancestors"]
                    ) + f"/{category['category__title_ru']}:{category['category__categoryId']}"

                    category[
                        "category__ancestors"
                    ] += f"/{category['category__title']}:{category['category__categoryId']}"
                elif category["category__categoryId"] == 1:
                    category["category__ancestors_ru"] = (
                        category["category__title_ru"] + f":{category['category__categoryId']}"
                    )
                    category["category__ancestors"] = (
                        category["category__title"] + f":{category['category__categoryId']}"
                    )
                category["category__title_ru"] = (
                    category["category__title_ru"] if category["category__title_ru"] else category["category__title"]
                ) + f"(({category['category__categoryId']}))"
                category["category__title"] += f"(({category['category__categoryId']}))"

                del category["category__categoryId"]

            print("NicheSelectionView took", time.time() - start)
            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": categories,
                    "total": len(categories),
                },
            )

        except Exception as e:
            print("Error in NicheSlectionView: ", e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


# Seller tariff
@method_decorator(csrf_protect, name="dispatch")
class GrowingCategoriesView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            print("Start GrowingProductsView")
            authorize_Seller_tariff(request)
            start = time.time()

            start_date = timezone.make_aware(
                datetime.combine(date.today() - timedelta(days=30), datetime.min.time()),
                timezone=pytz.timezone("Asia/Tashkent"),
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            date_pretty = get_today_pretty_fake()

            end_date = timezone.make_aware(
                datetime.combine(date.today(), datetime.min.time()),
                timezone=pytz.timezone("Asia/Tashkent"),
            ).replace(hour=23, minute=59, second=59, microsecond=0)

            top_growing_categories = cache.get("top_categories_by_orders", [])

            categories = (
                CategoryAnalytics.objects.select_related("product", "product__category", "product__shop")
                .filter(category__categoryId__in=top_growing_categories, created_at__range=[start_date, end_date])
                .values(
                    "category__categoryId",
                    "category__title",
                    "category__title_ru",
                    "category__created_at",
                    "category__descendants",
                    "average_purchase_price",
                    "average_product_rating",
                    "total_products",
                    "total_orders",
                    "total_reviews",
                    "total_shops",
                    "total_shops_with_sales",
                    "total_products_with_sales",
                    "date_pretty",
                    "total_orders_amount",
                    "created_at",
                )
                .order_by("category__categoryId", "date_pretty")
            )

            grouped_analytics = []
            for categoryId, group in groupby(categories, key=lambda x: x["category__categoryId"]):
                grouped_analytics.append(
                    {
                        "categoryId": categoryId,
                        "analytics": list(group),
                    }
                )
            print("Time taken for GrowingCategories", time.time() - start)
            return Response(grouped_analytics, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Seller tariff
class MainCategoriesAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request: Request):
        try:
            print("Start MainCategoriesAnalyticsView")
            authorize_Seller_tariff(request)

            start = time.time()

            user: User = request.user

            days = 60 if user.tariff == Tariffs.SELLER or user.tariff == Tariffs.BUSINESS else 30
            days = 90 if user.tariff == Tariffs.BUSINESS else days
            start_date = timezone.make_aware(
                datetime.combine(date.today() - timedelta(days=days), datetime.min.time()),
                timezone=pytz.timezone("Asia/Tashkent"),
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            main_category = Category.objects.get(categoryId=1)
            children = main_category.child_categories.all()

            if datetime.now().astimezone(pytz.timezone("Asia/Tashkent")).hour < 7:
                end_date = timezone.make_aware(
                    datetime.combine(date.today() - timedelta(days=1), datetime.min.time()),
                    timezone=pytz.timezone("Asia/Tashkent"),
                ).replace(hour=23, minute=59, second=59, microsecond=0)

            else:
                end_date = timezone.make_aware(
                    datetime.combine(date.today(), datetime.min.time()),
                    timezone=pytz.timezone("Asia/Tashkent"),
                ).replace(hour=23, minute=59, second=59, microsecond=0)

            analytics = (
                CategoryAnalytics.objects.filter(category__in=children, created_at__range=[start_date, end_date])
                .order_by("category__categoryId", "created_at")
                .values(
                    "category__categoryId",
                    "category__title",
                    "average_purchase_price",
                    "average_product_rating",
                    "total_products",
                    "total_orders",
                    "total_reviews",
                    "total_shops",
                    "total_shops_with_sales",
                    "total_products_with_sales",
                    "date_pretty",
                )
            )

            grouped_analytics = []
            for _, group in groupby(analytics, key=lambda x: x["category__categoryId"]):
                analytics = list(group)

                all_orders = []
                daily_orders = []
                all_products = []
                all_reviews = []
                daily_reviews = []
                all_shops = []
                shops_with_sales = []
                all_products_with_sales = []
                average_price = []

                prev_orders = analytics[0]["total_orders"]
                prev_reviews = analytics[0]["total_reviews"]

                i = 0
                while i < len(analytics):
                    # all_orders.append(analytics[i]["total_orders"])
                    all_orders.append({"x": analytics[i]["date_pretty"], "y": analytics[i]["total_orders"]})
                    # all_products.append(analytics[i]["total_products"])
                    all_products.append({"x": analytics[i]["date_pretty"], "y": analytics[i]["total_products"]})
                    # all_reviews.append(analytics[i]["total_reviews"])
                    all_reviews.append({"x": analytics[i]["date_pretty"], "y": analytics[i]["total_reviews"]})

                    # all_shops.append(analytics[i]["total_shops"])
                    all_shops.append({"x": analytics[i]["date_pretty"], "y": analytics[i]["total_shops"]})
                    # shops_with_sales.append(analytics[i]["total_shops_with_sales"])
                    shops_with_sales.append(
                        {"x": analytics[i]["date_pretty"], "y": analytics[i]["total_shops_with_sales"]}
                    )
                    # all_products_with_sales.append(analytics[i]["total_products_with_sales"])
                    all_products_with_sales.append(
                        {"x": analytics[i]["date_pretty"], "y": analytics[i]["total_products_with_sales"]}
                    )
                    # average_price.append(analytics[i]["average_purchase_price"])
                    average_price.append(
                        {
                            "x": analytics[i]["date_pretty"],
                            "y": math.floor(analytics[i]["average_purchase_price"])
                            if analytics[i]["average_purchase_price"]
                            else 0,
                        }
                    )

                    if i > 0:
                        # daily_orders.append(analytics[i]["total_orders"] - prev_orders)
                        daily_orders.append(
                            {"x": analytics[i]["date_pretty"], "y": analytics[i]["total_orders"] - prev_orders}
                        )
                        # daily_reviews.append(analytics[i]["total_reviews"] - prev_reviews)/
                        daily_reviews.append(
                            {"x": analytics[i]["date_pretty"], "y": analytics[i]["total_reviews"] - prev_reviews}
                        )

                    prev_orders = analytics[i]["total_orders"]
                    prev_reviews = analytics[i]["total_reviews"]

                    i += 1

                grouped_analytics.append(
                    {
                        "title": analytics[0]["category__title"],
                        "prices": average_price,
                        "orders": all_orders,
                        "daily_orders": daily_orders,
                        "products": all_products,
                        "reviews": all_reviews,
                        "daily_reviews": daily_reviews,
                        "shops": all_shops,
                        "shops_with_sales": shops_with_sales,
                        "products_with_sales": all_products_with_sales,
                    }
                )
            print("Time taken for Main Categories ", time.time() - start)
            return Response(grouped_analytics, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
