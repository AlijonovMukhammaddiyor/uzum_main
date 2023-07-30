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
from django.db.models import Avg, Count, Prefetch, Q, Sum
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from uzum.category.serializers import ProductAnalyticsViewSerializer
from uzum.jobs.constants import PRODUCT_HEADER
from uzum.jobs.helpers import generateUUID, get_random_user_agent
from uzum.product.models import Product, ProductAnalytics, ProductAnalyticsView
from uzum.product.pagination import ExamplePagination
from uzum.product.serializers import (
    CurrentProductSerializer,
    ExtendedProductAnalyticsSerializer,
    ExtendedProductSerializer,
    ProductSerializer,
)

from uzum.sku.models import SkuAnalytics
from uzum.users.models import User
from uzum.utils.general import check_user, get_today_pretty_fake


class ProductView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: int):
        try:
            if check_user(request) is None:
                return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "Forbidden"})

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


class AllProductsPriceSegmentationView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    # replace the below with your actual serializer
    # serializer_class = ProductAnalyticsSerializer
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
            # if check_user(request) is None:
            #     return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "Forbidden"})

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


class CurrentProductView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: str):
        try:
            if check_user(request) is None:
                return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "Forbidden"})
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


class ProductsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ProductAnalyticsViewSerializer
    pagination_class = ExamplePagination

    VALID_SORT_FIELDS = [
        "orders_amount",
        "reviews_amount",
        "product_available_amount",
        "rating",
        "position_in_category",
        "avg_purchase_price",
        "orders_money",
    ]
    VALID_FILTER_FIELDS = ["product_title", "product_title_ru", "shop_title", "category_title", "category_title_ru"]

    @extend_schema(tags=["Product"])
    def get_queryset(self):
        try:
            # Get query parameters
            start = time.time()
            column = self.request.query_params.get("column", "orders_money")  # default is 'orders_amount'
            order = self.request.query_params.get("order", "desc")  # default is 'asc'
            search_columns = self.request.query_params.get("searches", "")  # default is empty string
            filters = self.request.query_params.get("filters", "")  # default is empty string

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

                    # filter_query |= Q(**{f"{search_columns[i]}__icontains": filters[i]})
                    # it should be And not Or and case insensitive
                    filter_query &= Q(**{f"{search_columns[i]}__icontains": filters[i]})

            print("filter_query", filter_query)
            # Query the database
            data = ProductAnalyticsView.objects.filter(filter_query).order_by(column)
            print("Products query time", time.time() - start)
            return data
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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

            if check_user(request) is None:
                return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "Forbidden"})

            print("SingleProductAnalyticsView")
            user: User = request.user
            is_proplus = user.is_proplus
            days = 60 if is_proplus else 30

            # set to the 00:00 of 30 days ago in Asia/Tashkent timezone
            start_date = timezone.make_aware(
                datetime.combine(date.today() - timedelta(days=days), datetime.min.time()),
                timezone=pytz.timezone("Asia/Tashkent"),
            )

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
            user = check_user(request)
            if user is None:
                return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "Forbidden"})

            # is_proplus = user.is_proplus
            # days = 60 if is_proplus else 3
            days = 60

            productIds = SimilarProductsViewByUzum.fetch_similar_products_from_uzum(product_id)
            productIds.append(product_id)

            start_date = timezone.make_aware(
                datetime.combine(date.today() - timedelta(days=days), datetime.min.time()),
                timezone=pytz.timezone("Asia/Tashkent"),
            )

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
                product["product__category__title"] += f"(({product['product__category__categoryId']}))"
                product["product__shop__title"] += f"(({product['product__shop__link']}))"
                product["product__title"] += f"(({product['product__product_id']}))"

                product["product__title_ru"] += f"(({product['product__product_id']}))"
                product["product__category__title_ru"] += f"(({product['product__category__categoryId']}))"

            # group by product__product_id
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
            if check_user(request) is None:
                return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "Forbidden"})

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
            print("Start NewProductsView")
            if check_user(request) is None:
                return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "Forbidden"})
            elif not request.user.is_proplus:
                return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "Forbidden"})
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

                product["product__title_ru"] += f"(({product['product__product_id']}))"
                product["product__category__title_ru"] += f"(({product['product__category__categoryId']}))"

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

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            print("Start GrowingProductsView")
            if check_user(request) is None:
                return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "Forbidden"})
            elif not request.user.is_proplus:
                return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "Forbidden"})
            start = time.time()
            search_columns = request.query_params.get("searches", "")  # default is empty string
            filters = request.query_params.get("filters", "")  # default is empty string

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
            page = int(request.query_params.get("page", 1))
            start_date = timezone.make_aware(
                datetime.combine(date.today() - timedelta(days=30), datetime.min.time()),
                timezone=pytz.timezone("Asia/Tashkent"),
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            top_growing_products = cache.get("top_growing_products", [])
            paginator = Paginator(top_growing_products, 20)
            product_ids_page = paginator.get_page(page)

            products = (
                ProductAnalytics.objects.select_related("product", "product__category", "product__shop")
                .filter(product__product_id__in=product_ids_page, created_at__gte=start_date)
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
                        "product__category__title": last_analytics["product__category__title"]
                        + f"(({last_analytics['product__category__categoryId']}))",
                        "product__shop__title": last_analytics["product__shop__title"]
                        + f"(({last_analytics['product__shop__link']}))",
                        "position": last_analytics["position"],
                        "position_in_category": last_analytics["position_in_category"],
                        "orders": orders,
                        "reviews": reviews,
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
                    "count": products.count(),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
