import json
import logging
import time
import traceback
from datetime import date, datetime, timedelta
from itertools import groupby

import numpy as np
import pandas as pd
import pytz
import requests
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db import connection
from django.db.models import Avg, Count, F, Prefetch, Q, Sum
from django.db.models.functions import Abs
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import (LimitOffsetPagination,
                                       PageNumberPagination)
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from uzum.category.models import Category, CategoryAnalytics
from uzum.category.serializers import ProductAnalyticsViewSerializer
from uzum.jobs.constants import PRODUCT_HEADER
from uzum.jobs.helpers import generateUUID, get_random_user_agent
from uzum.product.models import Product, ProductAnalytics, ProductAnalyticsView
from uzum.product.pagination import ExamplePagination
from uzum.product.serializers import (CurrentProductSerializer,
                                      ExtendedProductAnalyticsSerializer,
                                      ExtendedProductSerializer,
                                      ProductSerializer)
from uzum.sku.models import SkuAnalytics
from uzum.users.models import User
from uzum.utils.general import (Tariffs, authorize_Base_tariff,
                                authorize_Seller_tariff, get_day_before_pretty,
                                get_days_based_on_tariff,
                                get_today_pretty_fake)

logger = logging.getLogger(__name__)


# Base tariff
class ProductView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: int):
        try:
            authorize_Base_tariff(request)
            product = Product.objects.get(product_id=product_id)

            return Response(
                {
                    "title": product.title,
                    "title_ru": product.title_ru,
                },
                status=status.HTTP_200_OK,
            )
        except Product.DoesNotExist as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            traceback.print_exc()
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Free tariff
class Top5ProductsView(APIView):
    permission_classes = [AllowAny]
    allowed_methods = ["GET"]
    serializer_class = ProductSerializer

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            date_pretty = request.query_params.get("date", get_today_pretty_fake())
            products = (
                ProductAnalytics.objects.filter(date_pretty=date_pretty)
                .order_by("-orders_amount")[:5]
                .values("product__title", "orders_amount", "product__title_ru")
            )
            return Response(products, status=status.HTTP_200_OK)
        except Exception as e:
            traceback.print_exc()
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class AllProductsPriceSegmentationView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    queryset = ProductAnalyticsView.objects.all()
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

    def get(self, request: Request):
        try:
            start_time = time.time()
            authorize_Base_tariff(request)
            segments_count = request.query_params.get("segments_count", 15)
            segments_count = int(segments_count)

            products = ProductAnalyticsView.objects.all()

            df = pd.DataFrame(list(products.values("product_id", "avg_purchase_price")))
            distinct_prices_count = df["avg_purchase_price"].nunique()
            segments_count = min(segments_count, distinct_prices_count)
            products_per_segment = len(df) // segments_count
            df = df.sort_values("avg_purchase_price")

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

            bins = [
                (np.floor(min_price / 1000) * 1000, np.ceil(max_price / 1000) * 1000) for min_price, max_price in bins
            ]

            segments = []
            for i in range(len(bins)):
                (segment_min_price, segment_max_price) = bins[i]
                segments.append(
                    self.calculate_segment(
                        segment_min_price,
                        segment_max_price,
                        products,
                    )
                )

            print(f"All Products Segmentation took {time.time() - start_time} seconds")
            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": segments,
                },
            )
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class CurrentProductView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: str):
        try:
            authorize_Base_tariff(request)
            start = time.time()
            if product_id is None:
                return Response({"error": "product_id is required"}, status=status.HTTP_400_BAD_REQUEST)

            product = Product.objects.prefetch_related("skus", "analytics", "skus__analytics").get(
                product_id=product_id
            )

            serializer = CurrentProductSerializer(product)

            print(f"CurrentProductView: {time.time() - start}")
            return Response(
                {
                    "product": serializer.data,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            traceback.print_exc()
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class ProductsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ProductAnalyticsViewSerializer
    pagination_class = LimitOffsetPagination
    # pagination_class = None

    VALID_SORT_FIELDS = [
        "orders_amount",
        "reviews_amount",
        "product_available_amount",
        "rating",
        "position_in_category",
        "avg_purchase_price",
        "orders_money",
        "revenue_3_days",
        "orders_3_days",
        "weekly_revenue",
        "weekly_orders",
        "monthly_revenue",
        "monthly_orders",
        "revenue_90_days",
        "orders_90_days"
    ]
    VALID_FILTER_FIELDS = ["product_title", "product_title_ru", "shop_title", "category_title", "category_title_ru"]

    @extend_schema(tags=["Product"])
    def get_queryset(self):
        try:
            start = time.time()
            # Extracting all query parameters
            params = self.request.GET

            # Dictionary to hold the actual ORM filters
            orm_filters = {}

            # Extracting sorting parameters
            column = params.get("column", "orders_money")  # Get the column to sort by
            order = params.get("order", "desc")  # Get the order (asc/desc)
            categories = params.get("categories", None)  # Get the categories to filter by

            weekly = params.get("weekly", None)  # Get the categories to filter by
            monthly = params.get("monthly", None)  # Get the categories to filter by

            if weekly:
                return ProductAnalyticsView.objects.all().order_by("-weekly_revenue")[:100]

            if monthly:
                return ProductAnalyticsView.objects.all().order_by("-monthly_revenue")[:100]

            if not categories:
                # return empty queryset
                return ProductAnalyticsView.objects.none()

            categories = map(int, categories.split(","))

            title_include_q_objects = Q()
            title_exclude_q_objects = Q()

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

                elif "title_include" in key:
                    # we got list of keywords to include in either title or title_ru
                    keywords = value.split("---")
                    for keyword in keywords:
                        if "ru" in key:
                            title_include_q_objects |= Q(product_title_ru__icontains=keyword)
                        else:
                            title_include_q_objects |= Q(product_title__icontains=keyword)

                elif "title_exclude" in key:
                    keywords = value.split("---")
                    # we got list of keywords to exclude in either title or title_ru
                    for keyword in keywords:
                        if "ru" in key:
                            title_exclude_q_objects &= ~Q(product_title_ru__icontains=keyword)
                        else:
                            title_exclude_q_objects &= ~Q(product_title__icontains=keyword)

                if key.startswith("product_created_at"):
                    # Convert the timestamp back to a datetime object with the correct timezone
                    values = orm_filters.get(key)
                    # check if values is list
                    if values and isinstance(values, list) or isinstance(values, tuple):
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

            logger.warning("Product filters %s", orm_filters)
            # # Now, use the orm_filters to query the database
            queryset = ProductAnalyticsView.objects.filter(
                title_include_q_objects, title_exclude_q_objects, **orm_filters, category_id__in=categories
            )

            if column:
                order_prefix = "-" if order == "desc" else ""  # Add "-" prefix for descending order
                queryset = queryset.order_by(order_prefix + column)

            # Query the database
            print("Products query time", time.time() - start)
            return queryset if queryset else ProductAnalyticsView.objects.none()
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    @extend_schema(tags=["Product"])
    def list(self, request: Request):
        authorize_Base_tariff(self.request)
        return super().list(request)


class ProductsToExcelView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request, category_id: str):
        try:
            authorize_Base_tariff(request)
            start = time.time()
            category = Category.objects.get(categoryId=category_id)
            categories = category.descendants
            if not categories:
                categories = [category_id]
            else:
                categories = categories.split(",")
                categories.append(category_id)
            params = self.request.GET

            # Dictionary to hold the actual ORM filters
            orm_filters = {}

            # Extracting sorting parameters
            column = params.get("column", "orders_money")  # Get the column to sort by
            order = params.get("order", "desc")  # Get the order (asc/desc)

            weekly = params.get("weekly", None)  # Get the categories to filter by
            monthly = params.get("monthly", None)  # Get the categories to filter by

            if weekly:
                return ProductAnalyticsView.objects.all().order_by("-weekly_orders_money")[:100]

            if monthly:
                return ProductAnalyticsView.objects.all().order_by("-diff_orders_money")[:100]

            if not categories:
                # return empty queryset
                return ProductAnalyticsView.objects.none()

            title_include_q_objects = Q()
            title_exclude_q_objects = Q()

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

                elif "title_include" in key:
                    # we got list of keywords to include in either title or title_ru
                    keywords = value.split("---")
                    for keyword in keywords:
                        if "ru" in key:
                            title_include_q_objects |= Q(product_title_ru__icontains=keyword)
                        else:
                            title_include_q_objects |= Q(product_title__icontains=keyword)

                elif "title_exclude" in key:
                    keywords = value.split("---")
                    # we got list of keywords to exclude in either title or title_ru
                    for keyword in keywords:
                        if "ru" in key:
                            title_exclude_q_objects &= ~Q(product_title_ru__icontains=keyword)
                        else:
                            title_exclude_q_objects &= ~Q(product_title__icontains=keyword)

                if key.startswith("orders_money") or key.startswith("diff_orders_money"):
                    # divide by 1000
                    values = orm_filters[key]
                    for keyword in keywords:
                        if "ru" in key:
                            title_exclude_q_objects &= ~Q(product_title_ru__iexact=keyword)
                        else:
                            title_exclude_q_objects &= ~Q(product_title__iexact=keyword)

                if key.startswith("product_created_at"):
                    # Convert the timestamp back to a datetime object with the correct timezone
                    values = orm_filters.get(key)
                    # check if values is list
                    print("right")
                    if values and isinstance(values, list) or isinstance(values, tuple):
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

            logger.warning("Product filters %s", orm_filters)
            # # Now, use the orm_filters to query the database
            queryset = ProductAnalyticsView.objects.filter(
                title_include_q_objects, title_exclude_q_objects, **orm_filters, category_id__in=categories
            )

            if column:
                order_prefix = "-" if order == "desc" else ""  # Add "-" prefix for descending order
                queryset = queryset.order_by(order_prefix + column)

            products = queryset.values(
                "product_id",
                "product_title_ru",
                "product_title",
                "orders_amount",
                "product_available_amount",
                "orders_money",
                "reviews_amount",
                "rating",
                "shop_title",
                "category_title",
                "category_title_ru",
                "avg_purchase_price",
                "position_in_category",
                "diff_orders_amount",
                "diff_orders_money",
                "diff_reviews_amount",
                "weekly_orders_amount",
                "weekly_orders_money",
                "weekly_reviews_amount",
            )

            logger.info(f"ProductsToExcelView: {time.time() - start}")

            return Response(
                data=products,
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            traceback.print_exc()
            return Response([])


# Base tariff
class SingleProductAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    # pagination_class = ExamplePagination
    # serializer_class = ExtendedProductSerializer

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: str):
        try:
            start = time.time()

            authorize_Base_tariff(request)
            print("SingleProductAnalyticsView")
            user: User = request.user
            days = get_days_based_on_tariff(user)
            # set to the 00:00 of 30 days ago in Asia/Tashkent timezone
            last_date = (
                ProductAnalytics.objects.filter(product__product_id=product_id)
                .order_by("-created_at")
                .first()
                .created_at
            )

            start_date = timezone.make_aware(
                datetime.combine(last_date - timedelta(days=days), datetime.min.time()),
                timezone=pytz.timezone("Asia/Tashkent"),
            )

            # start_date = timezone.make_aware(
            #     datetime.combine(date.today() - timedelta(days=days), datetime.min.time()),
            #     timezone=pytz.timezone("Asia/Tashkent"),
            # )

            if datetime.now().astimezone(pytz.timezone("Asia/Tashkent")).hour < 7:
                end_date = timezone.make_aware(
                    datetime.combine(date.today() - timedelta(days=1), datetime.min.time()),
                    timezone=pytz.timezone("Asia/Tashkent"),
                ).replace(hour=23, minute=59, second=59)
            else:
                end_date = timezone.make_aware(
                    datetime.combine(date.today(), datetime.min.time()),
                    timezone=pytz.timezone("Asia/Tashkent"),
                ).replace(hour=23, minute=59, second=59)

            product_analytics_qs = ProductAnalytics.objects.filter(
                product__product_id=product_id, created_at__range=[start_date, end_date]
            ).order_by("created_at")

            sku_analytics_qs = SkuAnalytics.objects.filter(
                sku__product__product_id=product_id, created_at__range=[start_date, end_date]
            ).order_by("created_at")

            product = (
                Product.objects.filter(product_id=product_id)
                .annotate(
                    skus_count=Count("skus"),
                )
                .prefetch_related(
                    Prefetch("analytics", queryset=product_analytics_qs, to_attr="recent_analytics"),
                    Prefetch("skus__analytics", queryset=sku_analytics_qs, to_attr="recent_analytics"),
                )
                .first()
            )

            if not product:
                return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)

            # Now, for each product in `products`, you can access `product.recent_analytics`
            # and `sku.recent_sku_analytics`
            # for each SKU in `product.skus.all()`, to get the analytics records since the start date.

            serializer = ExtendedProductAnalyticsSerializer(product)
            print("SingleProductAnalyticsView query time", time.time() - start)
            return Response(serializer.data, status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff with Some Seller tariff
class SimilarProductsViewByUzum(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination
    serializer_class = ExtendedProductSerializer

    @staticmethod
    def fetch_similar_products_from_uzum(product_id: str):
        try:
            response = requests.get(
                f"https://api.uzum.uz/api/v2/product/{product_id}/similar?size=100",
                headers={
                    **PRODUCT_HEADER,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
                timeout=60,  # 60 seconds
            )

            if response.status_code == 200:
                # extract product ids
                productIds = [product["productId"] for product in response.json()]
                return productIds
            else:
                return []

        except Exception as e:
            traceback.print_exc()
            return None

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: str):
        try:
            start = time.time()
            authorize_Base_tariff(request)

            days = 100

            start_date = timezone.make_aware(
                datetime.combine(date.today() - timedelta(days=days), datetime.min.time()),
                timezone=pytz.timezone("Asia/Tashkent"),
            )

            product = Product.objects.get(product_id=product_id)

            product_analytics = (
                ProductAnalytics.objects.filter(product=product, created_at__gte=start_date)
                .order_by("-created_at")
                .first()
            )

            if not product_analytics:
                return Response(status=201, data={"data": []})

            similar_products = (
                ProductAnalytics.objects.filter(
                    product__category=product.category, date_pretty=get_today_pretty_fake()
                )
                .exclude(product__shop__account_id=product.shop.account_id)
                .annotate(
                    diff_orders_money=Abs(F("orders_money") - product_analytics.orders_money),
                    diff_avg_purchase_price=Abs(
                        F("average_purchase_price") - product_analytics.average_purchase_price
                    ),
                )
                .order_by("diff_orders_money", "diff_avg_purchase_price")
                .values_list("product__product_id", flat=True)[:100]
            )

            productIds = list(similar_products)
            productIds.append(product_id)

            analytics = (
                ProductAnalytics.objects.select_related("product")
                .filter(product__product_id__in=productIds, created_at__gte=start_date)
                .order_by("product__product_id", "created_at")
                .values(
                    "product__product_id",
                    "product__title",
                    "product__title_ru",
                    "average_purchase_price",
                    "rating",
                    "orders_amount",
                    "orders_money",
                    "reviews_amount",
                    "product__created_at",
                    "available_amount",
                    "product__category__title",
                    "product__category__title_ru",
                    "position",
                    "position_in_category",
                    "date_pretty",
                    "product__shop__title",
                    "product__shop__link",
                    "product__category__categoryId",
                    "product__photos",
                )
            )

            for product in analytics:
                try:
                    # print(product["product__category__title"], product["product__category__categoryId"])
                    product["product__category__title"] += f"(({product['product__category__categoryId']}))"
                    product["product__shop__title"] += f"(({product['product__shop__link']}))"
                    product["product__title"] += f"(({product['product__product_id']}))"

                    product["product__title_ru"] = (
                        product["product__title_ru"]
                        if product["product__title_ru"]
                        else product["product__title"] + f"(({product['product__product_id']}))"
                    )
                    product["product__category__title_ru"] = (
                        product["product__category__title_ru"]
                        if product["product__category__title_ru"]
                        else product["product__category__title"] + f"(({product['product__category__categoryId']}))"
                    )
                except Exception as e:
                    print(e)
                    print(product)

            grouped_analytics = []
            for product_id, group in groupby(analytics, key=lambda x: x["product__product_id"]):
                grouped_analytics.append(
                    {
                        "product_id": product_id,
                        "analytics": list(group),
                    }
                )

            print("SimilarProductsViewByUzum query time", time.time() - start)
            return Response(
                {
                    "data": grouped_analytics,
                },
                status=status.HTTP_200_OK,
            )

        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductReviews(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination
    serializer_class = ExtendedProductSerializer

    @staticmethod
    def fetch_reviews_from_uzum(product_id: str):
        try:
            response = requests.get(
                f"https://api.uzum.uz/api/product/{product_id}/reviews?amount=9999&page=0",
                headers={
                    **PRODUCT_HEADER,
                    "User-Agent": get_random_user_agent(),
                    "x-iid": generateUUID(),
                },
                timeout=60,  # 60 seconds
            )

            if response.status_code == 200:
                # extract product ids
                return response.json()["payload"]
            else:
                return []

        except Exception as e:
            traceback.print_exc()
            return None

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: str):
        try:
            reviews = ProductReviews.fetch_reviews_from_uzum(product_id)
            #         reviews = ProductReviews.fetch_reviews_from_uzum(product_id)

            #         if not reviews:
            #             return Response({"error": "No reviews found"}, status=status.HTTP_404_NOT_FOUND)

            #         # extract reviews
            #         reviews = [review["review"] for review in reviews]

            #         # join all reviews
            #         reviews = " ".join(reviews)

            #         # remove punctuation
            #         reviews = re.sub(r"[^\w\s]", "", reviews)

            #         # remove numbers
            #         reviews = re.sub(r"\d+", "", reviews)

            #         # remove stop words
            #         with open("uzum/product/uz_stopwords.json", "r") as f:
            #             stopwords = json.load(f)

            #         reviews = [word for word in reviews.split() if word not in stopwords]

            #         # count words
            #         word_count = Counter(reviews)

            #         # get top 10 words
            #         top_words = word_count.most_common(10)

            return Response(reviews, status=status.HTTP_200_OK)

        except Product.DoesNotExist:
            return Response({"error": "Product not found"}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductsWithMostRevenueYesterdayView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request: Request):
        try:
            start = time.time()
            date_pretty = get_today_pretty_fake()
            yesterday_pretty = get_day_before_pretty(date_pretty)

            # Get the count of products with sales yesterday
            product_with_no_sales = ProductAnalytics.objects.filter(date_pretty=date_pretty, orders_amount=0).count()
            products_with_no_reviews = ProductAnalytics.objects.filter(
                date_pretty=date_pretty, reviews_amount=0
            ).count()

            def dictfetchall(cursor):
                "Returns all rows from a cursor as a dict"
                desc = cursor.description
                return [dict(zip([col[0] for col in desc], row)) for row in cursor.fetchall()]

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(DISTINCT today.product_id) as products_with_sales_yesterday
                    FROM
                        product_productanalytics AS today
                    JOIN
                        product_productanalytics AS yesterday
                    ON
                        today.product_id = yesterday.product_id
                    AND
                        today.date_pretty = %s
                    AND
                        yesterday.date_pretty = %s
                    WHERE
                        today.orders_amount - COALESCE(yesterday.orders_amount, 0) > 0;
                    """,
                    [date_pretty, yesterday_pretty],
                )

                res = dictfetchall(cursor)
                products_with_sales_yesterday = res[0]["products_with_sales_yesterday"]

                cursor.execute(
                    """
                    SELECT
                        COUNT(DISTINCT today.product_id) as products_with_reviews_yesterday
                    FROM
                        product_productanalytics AS today
                    JOIN
                        product_productanalytics AS yesterday
                    ON
                        today.product_id = yesterday.product_id
                    AND
                        today.date_pretty = %s
                    AND
                        yesterday.date_pretty = %s
                    WHERE
                        today.reviews_amount - COALESCE(yesterday.reviews_amount, 0) > 0
                                        """,
                    [date_pretty, yesterday_pretty],
                )

                res = dictfetchall(cursor)
                products_with_reviews_yesterday = res[0]["products_with_reviews_yesterday"]

                cursor.execute(
                    """
                    SELECT
                        today.product_id,
                        today.orders_money - COALESCE(yesterday.orders_money, 0) as diff_revenue
                    FROM
                        (
                        SELECT
                            product_id,
                            orders_money
                        FROM
                            product_productanalytics
                        WHERE
                            date_pretty = %s
                        ) as today
                    INNER JOIN
                        (
                        SELECT
                            product_id,
                            orders_money
                        FROM
                            product_productanalytics
                        WHERE
                            date_pretty = %s
                        ) as yesterday
                    ON
                        today.product_id = yesterday.product_id
                    ORDER BY
                        diff_revenue DESC
                    LIMIT 5;
                """,
                    [date_pretty, yesterday_pretty],
                )

                res = dictfetchall(cursor)

                product_ids = [row["product_id"] for row in res]
                product_ids_tuple = tuple(product_ids)
                start_date = timezone.make_aware(
                    datetime.now() - timedelta(days=7), timezone=pytz.timezone("Asia/Tashkent")
                ).replace(hour=0, minute=0, second=0, microsecond=0)
                end_date = timezone.make_aware(
                    datetime.strptime(date_pretty, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
                ).replace(hour=23, minute=59, second=59, microsecond=999999)

                cursor.execute(
                    """
                    SELECT
                        pa.product_id,
                        pa.orders_amount,
                        pa.reviews_amount,
                        pa.orders_money,
                        pa.average_purchase_price,
                        pa.rating,
                        pa.date_pretty,
                        pp.title AS product_title,
                        pp.title_ru AS product_title_ru,
                        cat."categoryId" AS category_id,
                        cat.title AS category_title,
                        cat.title_ru AS category_title_ru,
                        shop.seller_id AS shop_id,
                        shop.title AS shop_title
                    FROM
                        product_productanalytics AS pa
                    JOIN
                        product_product AS pp ON pa.product_id = pp.product_id
                    JOIN
                        category_category AS cat ON pp.category_id = cat."categoryId"  -- Adjust the table and column names as necessary
                    JOIN
                        shop_shop AS shop ON pp.shop_id = shop.seller_id        -- Adjust the table and column names as necessary
                    WHERE
                        pa.product_id IN %s AND pa.created_at >= %s AND pa.created_at <= %s
                    ORDER BY
                        pa.product_id, pa.date_pretty DESC
                    """,
                    [product_ids_tuple, start_date, end_date],
                )
                rows = dictfetchall(cursor)

                # Group results by shop_id
                grouped_data = []
                for row in rows:
                    product_id = row["product_id"]

                    # Check if the product is already in the grouped_data list
                    product_entry = next((item for item in grouped_data if item["id"] == product_id), None)

                    if not product_entry:
                        # If not, create a new product entry
                        product_entry = {
                            "id": product_id,
                            "title": row["product_title"] + f"(({product_id}))",
                            "title_ru": (row["product_title_ru"] if row["product_title_ru"] else row["product_title"])
                            + f"(({product_id}))",
                            "category_id": row["category_id"],
                            "category_title": row["category_title"] + f"(({row['category_id']}))",
                            "category_title_ru": (
                                row["category_title_ru"] if row["category_title_ru"] else row["category_title"]
                            )
                            + f"(({row['category_id']}))",
                            "shop_id": row["shop_id"],
                            "shop_title": row["shop_title"] + f"(({row['shop_id']}))",
                            "orders_amount": row["orders_amount"],
                            "reviews_amount": row["reviews_amount"],
                            "orders_money": [row["orders_money"]],  # Initialize with the current order_money in a list
                            "average_purchase_price": row["average_purchase_price"],
                            "rating": row["rating"],
                            "date_pretty": row["date_pretty"],
                        }
                        grouped_data.append(product_entry)
                    else:
                        # If the product entry exists, just append the orders_money to the list
                        product_entry["orders_money"].append(row["orders_money"])
            print("Products with most revenue yesterday took", time.time() - start, "seconds")

            return Response(
                {
                    "product_with_no_sales": product_with_no_sales,
                    "products_with_sales_yesterday": products_with_sales_yesterday,
                    "top_products": grouped_data,
                    "products_with_reviews_yesterday": products_with_reviews_yesterday,
                    "products_with_no_reviews": products_with_no_reviews,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Seller tariff
class NewProductsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    VALID_SORT_FIELDS = [
        "orders_amount",
        "reviews_amount",
        "product_available_amount",
        "rating",
        "position_in_category",
        "average_purchase_price",
        "product__created_at",
    ]
    VALID_FILTER_FIELDS = [
        "product__title",
        "product__title_ru",
        "product__shop__title",
        "product__category__title",
        "product__category__title_ru",
    ]

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            authorize_Seller_tariff(request)
            print("Start NewProductsView")
            start = time.time()
            column = request.query_params.get("column", "orders_amount")  # default is 'orders_amount'
            order = request.query_params.get("order", "desc")  # default is 'desc'
            search_columns = request.query_params.get("searches", "")  # default is empty string
            filters = request.query_params.get("filters", "")  # default is empty string

            # Validate sorting
            if column not in self.VALID_SORT_FIELDS:
                raise ValidationError({"error": f"Invalid column: {column}"})

            if order not in ["asc", "desc"]:
                raise ValidationError({"error": f"Invalid order: {order}"})

            # Determine sorting order
            if order == "desc":
                column = "-" + column

            # Build filter query
            filter_query = Q()
            if search_columns and filters:
                search_columns = search_columns.split(",")
                filters = filters.split("---")

                if len(search_columns) != len(filters):
                    raise ValidationError({"error": "Number of search columns and filters does not match"})

                for i in range(len(search_columns)):
                    if search_columns[i] not in self.VALID_FILTER_FIELDS:
                        raise ValidationError({"error": f"Invalid search column: {search_columns[i]}"})

                    filter_query &= Q(**{f"{search_columns[i]}__icontains": filters[i]})

            # get the recent products created last week
            start_date = timezone.make_aware(
                datetime.combine(date.today() - timedelta(days=3), datetime.min.time()),
            ).replace(tzinfo=pytz.timezone("Asia/Tashkent"))

            products = (
                ProductAnalytics.objects.select_related("product", "product__category", "product__shop")
                .filter(date_pretty=get_today_pretty_fake(), product__created_at__gte=start_date)
                .filter(filter_query)
                .values(
                    "product__product_id",
                    "product__title",
                    "product__title_ru",
                    "product__created_at",
                    "product__photos",
                    "product__category__categoryId",
                    "product__category__title",
                    "product__category__title_ru",
                    "product__shop__link",
                    "product__shop__title",
                    "average_purchase_price",
                    "rating",
                    "orders_amount",
                    "orders_money",
                    "reviews_amount",
                    "available_amount",
                    "position",
                    "position_in_category",
                    "date_pretty",
                )
            ).order_by(column, "-product__created_at")

            paginator = Paginator(products, 20)
            page_number = request.query_params.get("page", 1)
            page_obj = paginator.get_page(page_number)

            # add category_id to category__title -> product__category__title + (categoryId)
            for product in page_obj:
                product["product__category__title"] += f"(({product['product__category__categoryId']}))"
                product["product__shop__title"] += f"(({product['product__shop__link']}))"
                product["product__title"] += f"(({product['product__product_id']}))"

                product["product__title_ru"] = (
                    product["product__title_ru"] if product["product__title_ru"] else product["product__title"]
                ) + f"(({product['product__product_id']}))"
                product["product__category__title_ru"] = (
                    product["product__category__title_ru"]
                    if product["product__category__title_ru"]
                    else product["product__category__title"]
                ) + f"(({product['product__category__categoryId']}))"

            # Get the total count of matching products
            print("Time taken for NewProductsView", time.time() - start)
            return Response(
                {
                    "results": list(page_obj),
                    "count": products.count(),
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Seller tariff
class GrowingProductsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    pagination_class = ExamplePagination
    VALID_FILTER_FIELDS = [
        "product__title",
        "product__title_ru",
        "product__shop__title",
        "product__category__title",
        "product__category__title_ru",
    ]
    VALID_SORT_FIELDS = [
        "orders_amount",
        "reviews_amount",
        "product_available_amount",
        "rating",
        "position_in_category",
        "average_purchase_price",
        "product__created_at",
    ]

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            print("Start GrowingProductsView")
            authorize_Seller_tariff(request)
            start = time.time()
            column = request.query_params.get("column", "orders_amount")  # default is 'orders_amount'
            order = request.query_params.get("order", "desc")  # default is 'desc'

            search_columns = request.query_params.get("searches", "")  # default is empty string
            filters = request.query_params.get("filters", "")  # default is empty string

            # Validate sorting
            if column not in self.VALID_SORT_FIELDS:
                raise ValidationError({"error": f"Invalid column: {column}"})

            if order not in ["asc", "desc"]:
                raise ValidationError({"error": f"Invalid order: {order}"})

            # Determine sorting order
            if order == "desc":
                column = "-" + column

            # Build filter query
            filter_query = Q()
            if search_columns and filters:
                search_columns = search_columns.split(",")
                filters = filters.split("---")

                if len(search_columns) != len(filters):
                    raise ValidationError({"error": "Number of search columns and filters does not match"})

                for i in range(len(search_columns)):
                    if search_columns[i] not in self.VALID_FILTER_FIELDS:
                        raise ValidationError({"error": f"Invalid search column: {search_columns[i]}"})

                    filter_query &= Q(**{f"{search_columns[i]}__icontains": filters[i]})
            start_date = timezone.make_aware(
                datetime.combine(date.today() - timedelta(days=30), datetime.min.time()),
                timezone=pytz.timezone("Asia/Tashkent"),
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            top_growing_products = cache.get("top_growing_products", [])
            product_ids_page = top_growing_products
            page = request.query_params.get("page", 1)

            pages = Paginator(product_ids_page, 20)

            data = pages.get_page(page)

            products = (
                ProductAnalytics.objects.select_related("product", "product__category", "product__shop")
                .filter(product__product_id__in=data, created_at__gte=start_date)
                .filter(filter_query)
                .values(
                    "product__product_id",
                    "product__title",
                    "product__title_ru",
                    "product__created_at",
                    "product__photos",
                    "product__category__categoryId",
                    "product__category__title",
                    "product__category__title_ru",
                    "product__shop__link",
                    "product__shop__title",
                    "average_purchase_price",
                    "rating",
                    "orders_amount",
                    "reviews_amount",
                    "available_amount",
                    "position",
                    "position_in_category",
                    "date_pretty",
                    "created_at",
                    "score",
                )
                .order_by("product__product_id", "created_at")
            )

            grouped_analytics = []
            for product_id, group in groupby(products, key=lambda x: x["product__product_id"]):
                analytics = list(group)
                last_analytics = analytics[-1]
                prev_orders = analytics[0]["orders_amount"]

                i = 1
                orders = []
                reviews = []
                available_amount = []

                while i < len(analytics):
                    orders.append({"y": analytics[i]["orders_amount"] - prev_orders, "x": analytics[i]["date_pretty"]})
                    reviews.append({"y": analytics[i]["reviews_amount"], "x": analytics[i]["date_pretty"]})
                    available_amount.append(
                        {
                            "y": analytics[i]["available_amount"],
                            "x": analytics[i]["date_pretty"],
                        }
                    )
                    prev_orders = analytics[i]["orders_amount"]

                    i += 1

                grouped_analytics.append(
                    {
                        "product_id": product_id,
                        "product__title": last_analytics["product__title"]
                        + f"(({last_analytics['product__product_id']}))",
                        "product__title_ru": (
                            last_analytics["product__title_ru"]
                            if last_analytics["product__title_ru"]
                            else last_analytics["product__title"]
                        )
                        + f"(({last_analytics['product__product_id']}))",
                        "product__category__title": last_analytics["product__category__title"]
                        + f"(({last_analytics['product__category__categoryId']}))",
                        "product__category__title_ru": (
                            last_analytics["product__category__title_ru"]
                            if last_analytics["product__category__title_ru"]
                            else last_analytics["product__category__title"]
                        )
                        + f"(({last_analytics['product__category__categoryId']}))",
                        "product__shop__title": last_analytics["product__shop__title"]
                        + f"(({last_analytics['product__shop__link']}))",
                        "position": last_analytics["position"],
                        "position_in_category": last_analytics["position_in_category"],
                        "orders_amount": orders,
                        "reviews_amount": reviews,
                        "available_amount": available_amount,
                        "average_purchase_price": last_analytics["average_purchase_price"],
                        "product__created_at": last_analytics["product__created_at"],
                        "photos": last_analytics["product__photos"],
                        "rating": last_analytics["rating"],
                    }
                )
            print("Time taken for GrowingProductsView", time.time() - start)

            return Response(
                {
                    "results": grouped_analytics,
                    "count": 100,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductDiscoveryView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            categories = request.query_params.get("categories", "")
            if not categories:
                return Response({"error": "Categories not provided"}, status=status.HTTP_400_BAD_REQUEST)
            min_avg_orders_count = request.query_params.get("min_avg_orders_count", 0)
            max_avg_orders_count = request.query_params.get("max_avg_orders_count", 999999999)
            min_total_orders_count = request.query_params.get("total_orders_count", 0)
            max_total_orders_count = request.query_params.get("total_orders_count", 999999999)
            # min_avg_

        except Exception as e:
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
