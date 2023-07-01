import json
import time
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytz
from django.core.cache import cache
from django.db import transaction
from django.db.models import Avg, Count, OuterRef, Q, Subquery, Sum, Value, F, Func, JSONField
from django.contrib.postgres.aggregates import ArrayAgg
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.generics import ListAPIView
from uzum.category.pagination import CategoryProductsPagination
from django.shortcuts import get_object_or_404
from django.db.models.functions import Cast

from uzum.category.utils import calculate_shop_analytics_in_category
from uzum.product.models import Product, ProductAnalytics, ProductAnalyticsView, get_today_pretty
from uzum.sku.models import Sku, SkuAnalytics

from .models import Category, CategoryAnalytics
from .serializers import CategoryProductsSerializer, ProductAnalyticsViewSerializer, CategorySerializer


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
            print("category tree")
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


class CategoryProductsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ProductAnalyticsViewSerializer
    pagination_class = CategoryProductsPagination

    def get_queryset(self):
        """
        This view should return a list of all the products for
        the category as determined by the category portion of the URL.
        """
        category_id = self.kwargs["category_id"]
        # Get the category
        category = get_object_or_404(Category, pk=category_id)
        date_pretty = get_today_pretty()
        # Get the descendant category IDs as a list of integers
        descendant_ids = list(map(int, category.descendants.split(",")))

        # Add the parent category ID to the list
        descendant_ids.append(category_id)

        return ProductAnalyticsView.objects.filter(category_id__in=descendant_ids).order_by("-orders_amount")

    def list(self, request, *args, **kwargs):
        start_time = time.time()
        print("CATEGORY PRODUCTS")
        response = super().list(request, *args, **kwargs)
        print(f"CATEGORY PRODUCTS: {time.time() - start_time} seconds")
        return response


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
            today = timezone.now()

            today_analytics = ProductAnalytics.objects.filter(
                product=OuterRef("pk"), date_pretty=today.strftime("%Y-%m-%d")
            )
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
                sku__product_id=OuterRef("product_id"), date_pretty=today.strftime("%Y-%m-%d")
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
            start_time = time.time()

            category = Category.objects.get(categoryId=category_id)
            category_products = self.get_category_products_comparison(category)

            paginator = self.pagination_class()  # new lines

            page = paginator.paginate_queryset(category_products, request)
            print(f"CATEGORY PRODUCTS: {time.time() - start_time} seconds")
            if page is not None:
                return paginator.get_paginated_response(page)

            print("Page is None")
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


class CategoryDailyAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @staticmethod
    def analytics(categories: list[Category], start_date: datetime):
        try:
            products_in_category = Product.objects.filter(category__in=categories)

            sku_analytics = SkuAnalytics.objects.filter(
                sku__product__in=products_in_category,
                created_at__lte=start_date,
            ).aggregate(
                avg_purchase_price=Avg("purchase_price"),
                avg_full_price=Avg("full_price"),
            )

            category_analytics = (
                CategoryAnalytics.objects.filter(
                    category__in=categories,
                    created_at__lte=start_date,
                )
                .order_by("created_at")
                .values(
                    "date_pretty",
                    "total_orders_amount",
                    "total_reviews",
                    "total_products",
                    "total_shops",
                    "total_shops_with_sales",
                    "total_products_with_sales",
                    "average_product_rating",
                )
            )

            for ca in category_analytics:
                ca.update(sku_analytics)

            return list(category_analytics)

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
                "total_available_amount": 10,
                "products_with_zero_available_amount": 10,
                "shops_count": 10,
                "average_purchase_price": 10.0,
                "average_full_price": 10.0,
                "average_rating":  5
                "products_with_sales": 10,
                "shops_with_sales": 10,
                "reviews_amount": 10,
            }]
        """
        try:
            range = request.query_params.get("range", 15)
            # get start_date 00:00 in Asia/Tashkent timezone which is range days ago
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=int(range)), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            # start_date = timezone.make_aware(
            #     datetime.strptime(start_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            # )
            # end_date = timezone.make_aware(
            #     datetime.strptime(end_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            # )

            category = Category.objects.get(categoryId=category_id)
            categories = category.get_category_descendants(include_self=True)

            category_analytics = self.analytics(categories, start_date)

            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": category_analytics,
                    "total": len(category_analytics),
                },
            )

        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class SubcategoriesView(APIView):
    """
    This class implements CategoryAnalytics for each subcategory.
    Args:
        APIView (_type_): _description_
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @staticmethod
    def analytics(subcategory: Category, start_date: datetime, end_date: datetime):
        try:
            categories = subcategory.get_category_descendants(include_self=True)
            products_in_category = Product.objects.filter(category__in=categories)

            sku_analytics = SkuAnalytics.objects.filter(
                sku__product__in=products_in_category,
                created_at__range=(start_date, end_date),
            ).aggregate(
                avg_purchase_price=Avg("purchase_price"),
                avg_full_price=Avg("full_price"),
                zero_available_count=Count("id", filter=Q(available_amount=0)),
            )

            category_analytics = (
                CategoryAnalytics.objects.filter(
                    category__in=categories,
                    created_at__range=(start_date, end_date),
                )
                .order_by("created_at")
                .values(
                    "date_pretty",
                    "total_orders_amount",
                    "total_reviews",
                    "total_products",
                    "total_shops",
                    "total_shops_with_sales",
                    "total_products_with_sales",
                    "total_products_with_reviews",
                    "average_product_rating",
                )
            )

            for ca in category_analytics:
                ca.update(sku_analytics)

            # add subcategory title and id
            for ca in category_analytics:
                ca.update({"subcategory_id": subcategory.categoryId, "subcategory_title": subcategory.title})

            return list(category_analytics)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return []

    @extend_schema(tags=["Category"])
    def get(self, request: Request, category_id):
        try:
            start_date_str = request.query_params.get("start_date")
            end_date_str = request.query_params.get("end_date")

            start_date = timezone.make_aware(
                datetime.strptime(start_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            )
            end_date = timezone.make_aware(
                datetime.strptime(end_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            )

            category = Category.objects.get(categoryId=category_id)
            children = category.children.all()

            if not children:
                return Response(status=status.HTTP_200_OK, data={"data": []})

            res = []

            # for child in children:
            #     category_analytics = self.analytics(child, start_date, end_date)
            #     res.append(category_analytics)

            # use threads instead of for loop

            with ThreadPoolExecutor() as executor:
                futures = [executor.submit(self.analytics, child, start_date, end_date) for child in children]
                for future in as_completed(futures):
                    res.append(future.result())

            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": res,
                    "total": len(res),
                },
            )
        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CategoryPriceSegmentationView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @staticmethod
    @transaction.atomic
    def segmentation_by_price(category: Category, start_date: datetime, end_date: datetime, segments_count: int):
        try:
            # get lowest and highest prices in category
            categories = category.get_category_descendants(include_self=True)
            # Aggregate product prices
            products = Product.objects.filter(
                category__in=categories,
            ).annotate(
                avg_price=Avg("skus__analytics__purchase_price"),  # get average price across all SKUs of a product
            )

            start_time = time.time()
            df = pd.DataFrame(list(products.values("product_id", "avg_price")))

            # Calculate quantiles
            quantiles = np.linspace(0, 1, segments_count + 1)
            bins = df["avg_price"].quantile(quantiles).values
            print("Quantiles calculated in", time.time() - start_time, "seconds")

            segments = []

            with ThreadPoolExecutor(max_workers=segments_count) as executor:
                futures = []

                for i in range(segments_count):
                    segment_min_price = bins[i]
                    segment_max_price = bins[i + 1]
                    futures.append(
                        executor.submit(
                            CategoryPriceSegmentationView.calculate_segment,
                            segment_min_price,
                            segment_max_price,
                            start_date,
                            end_date,
                            products,
                        )
                    )

                for future in as_completed(futures):
                    segments.append(future.result())

            return segments
        except Exception as e:
            print(e)
            traceback.print_exc()
            return []

    @staticmethod
    def calculate_segment(segment_min_price, segment_max_price, start_date, end_date, products):
        segment_products = products.filter(avg_price__range=(segment_min_price, segment_max_price))

        start_orders = ProductAnalytics.objects.filter(
            created_at=start_date,
            product__in=segment_products,
        ).aggregate(
            total_orders=Sum("orders_amount")
        )["total_orders"]

        end_orders = ProductAnalytics.objects.filter(
            created_at=end_date,
            product__in=segment_products,
        ).aggregate(
            total_orders=Sum("orders_amount")
        )["total_orders"]

        # Calculate the difference in total orders
        total_orders_delta = end_orders - start_orders if start_orders and end_orders else 0

        segment_analytics = ProductAnalytics.objects.filter(
            product__in=segment_products,
            created_at__range=(start_date, end_date),
        ).aggregate(
            total_products=Count("product_id", distinct=True),
            new_products=Count(
                "product_id", filter=Q(product__created_at__range=(start_date, end_date)), distinct=True
            ),
            total_shops=Count("product__shop", distinct=True),
            new_shops=Count(
                "product__shop",
                filter=Q(product__shop__created_at__range=(start_date, end_date)),
                distinct=True,
            ),
            total_shops_with_sales=Count("product__shop", filter=Q(orders_amount__gt=0), distinct=True),
            total_products_with_sales=Count("product_id", filter=Q(orders_amount__gt=0), distinct=True),
            average_purchase_price=Avg("orders_money"),
        )

        return {
            "from": segment_min_price,
            "to": segment_max_price,
            **segment_analytics,
            "total_orders": total_orders_delta,
        }

    @extend_schema(tags=["Category"])
    def get(self, request: Request, category_id):
        """
        For this endpoint, we need to get the following data:
        -
        Args:
            request (Request): _description_
            category_id (_type_): _description_

        Returns:
            [{
                from: 0,
                to: $100,
                total_orders: 100,
                new-products: 100, # How: CategoryAnalytics.total_products now - CategoryAnalytics.total_products before
                total_products: 100, # How: CategoryAnalytics.total_products now
                total_shops: 100, # How: CategoryAnalytics.total_shops now
                new_shops: 100, # How: CategoryAnalytics.total_shops now - CategoryAnalytics.total_shops before
                total_shops_with_sales: 100,
                total_products_with_sales: 100,
                average_price_per_order: 100,
            }]
        """
        try:
            start_time = time.time()
            start_date_str = request.query_params.get("start_date")
            end_date_str = request.query_params.get("end_date")
            segments_count = request.query_params.get("segments_count")
            if not segments_count:
                segments_count = 15
            else:
                segments_count = int(segments_count)

            start_date = timezone.make_aware(
                datetime.strptime(start_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            )
            end_date = timezone.make_aware(
                datetime.strptime(end_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            )

            category = Category.objects.get(categoryId=category_id)

            category_analytics = self.segmentation_by_price(category, start_date, end_date, segments_count)
            print(f"Category analytics took {time.time() - start_time} seconds")
            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": category_analytics,
                },
            )

        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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
        """
        For this endpoint, we need to get the following data:
        -
        Args:
            request (Request): request should contain start_date and end_date
            category_id (_type_): categoryId

        Returns:
            [{
                shop_title: "Shop title",
                shop_id: 1,

            }]
        """
        try:
            start_time = time.time()
            start_date_str = request.query_params.get("start_date")
            end_date_str = request.query_params.get("end_date")

            start_date = timezone.make_aware(
                datetime.strptime(start_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            )
            end_date = timezone.make_aware(
                datetime.strptime(end_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            )

            category = Category.objects.get(categoryId=category_id)

            category_analytics = self.shops_share(category, start_date, end_date)

            print(f"Category shops took {time.time() - start_time} seconds")
            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": category_analytics,
                },
            )

        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class NicheSlectionView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = CategorySerializer
    queryset = Category.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    def get(self, request):
        """
        Based on category analytics, returns the list of categories that are suitable for the niche
        Args:
            request (_type_): _description_

        Returns:
            _type_: _description_
        """
        try:
            term = request.query_params.get("term")

            categories = Category.objects.filter(title__icontains=term).values("categoryId", "title")

            return Response(status=status.HTTP_200_OK, data=categories)
        except Exception as e:
            print("Error in NicheSlectionView: ", e)
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})
