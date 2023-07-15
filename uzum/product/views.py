import time
import traceback
from datetime import date, datetime, timedelta
from itertools import groupby

import pandas as pd
import pytz
import requests
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import Avg, Count, OuterRef, Prefetch, Q, Subquery
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
from uzum.review.views import CookieJWTAuthentication
from uzum.sku.models import SkuAnalytics
from uzum.utils.general import get_day_before_pretty, get_today_pretty, get_today_pretty_fake


class ProductView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: int):
        try:
            product = Product.objects.get(product_id=product_id)

            return Response(
                {
                    "title": product.title,
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
                .values("product__title", "orders_amount")
            )
            return Response(products, status=status.HTTP_200_OK)
        except Exception as e:
            traceback.print_exc()
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ProductsSegmentationView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            max_price = request.query_params.get("max_price", None)
            if max_price is not None:
                max_price = float(max_price)
            else:
                max_price = 1000000000
            min_price = request.query_params.get("min_price", None)
            if min_price is not None:
                min_price = float(min_price)
            else:
                min_price = 0

            start_date_str = request.query_params.get("start_date", None)
            if start_date_str is None:
                date_pretty = get_today_pretty()
            else:
                date_pretty = start_date_str

            segments_count = int(request.query_params.get("segments_count", 20))
            sku_analytics = SkuAnalytics.objects.filter(
                date_pretty=date_pretty, purchase_price__gte=min_price, purchase_price__lte=max_price
            )

            if not sku_analytics.exists():
                date_pretty = get_day_before_pretty(date_pretty)
                sku_analytics = SkuAnalytics.objects.filter(
                    date_pretty=date_pretty, purchase_price__gte=min_price, purchase_price__lte=max_price
                )

            if not sku_analytics.exists():
                return Response({"error": "No data for today and yesterday"}, status=status.HTTP_404_NOT_FOUND)

            # product_analytics = ProductAnalytics.objects.filter(date_pretty=date_pretty).only(
            #     "product__product_id", "orders_amount"
            # )

            purchase_prices = sku_analytics.values("sku__product__product_id").annotate(
                avg_purchase_price=Avg("purchase_price"),
                orders_amount=Subquery(
                    ProductAnalytics.objects.filter(
                        product__product_id=OuterRef("sku__product__product_id"), date_pretty=date_pretty
                    ).values("orders_amount")[:1]
                ),
            )

            # Create a DataFrame from queryset
            df = pd.DataFrame(purchase_prices)

            # Generate bins with pandas qcut
            df["segment"], bins = pd.qcut(
                df["avg_purchase_price"], segments_count, labels=False, retbins=True, duplicates="drop"
            )

            # Count number of products in each segment
            segment_counts = df.groupby("segment")["sku__product__product_id"].count().sort_index()

            # Calculate total number of orders for each segment
            segment_orders = df.groupby("segment")["orders_amount"].sum().sort_index()

            # Generate response data
            response_data = [
                {
                    "segment": i,
                    "min": bins[i],
                    "max": bins[i + 1],
                    "count": segment_counts[i],
                    "orders": segment_orders[i],
                }
                for i in range(len(bins) - 1)
            ]

            total = 0

            for i in range(len(response_data)):
                total += response_data[i]["orders"]

            return Response({"data": response_data}, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CurrentProductView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request, product_id: str):
        try:
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
    ]
    VALID_FILTER_FIELDS = ["product_title", "shop_title", "category_title"]

    @extend_schema(tags=["Product"])
    def get_queryset(self):
        try:
            # Get query parameters
            start = time.time()
            column = self.request.query_params.get("column", "orders_amount")  # default is 'orders_amount'
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
            print("SingleProductAnalyticsView")
            start_date_str = request.query_params.get("start_date", None)

            if not start_date_str:
                # set to the 00:00 of 30 days ago in Asia/Tashkent timezone
                start_date = timezone.make_aware(
                    datetime.combine(date.today() - timedelta(days=48), datetime.min.time()),
                    timezone=pytz.timezone("Asia/Tashkent"),
                )
            else:
                start_date = timezone.make_aware(
                    datetime.combine(datetime.strptime(start_date_str, "%Y-%m-%d"), datetime.min.time()),
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

            productIds = SimilarProductsViewByUzum.fetch_similar_products_from_uzum(product_id)
            productIds.append(product_id)

            start_date = timezone.make_aware(
                datetime.combine(date.today() - timedelta(days=45), datetime.min.time()),
                timezone=pytz.timezone("Asia/Tashkent"),
            )

            analytics = (
                ProductAnalytics.objects.select_related("product")
                .filter(product__product_id__in=productIds, created_at__gte=start_date)
                .order_by("product__product_id", "created_at")
                .values(
                    "product__product_id",
                    "product__title",
                    "average_purchase_price",
                    "rating",
                    "orders_amount",
                    "reviews_amount",
                    "product__created_at",
                    "available_amount",
                    "product__category__title",
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
    VALID_FILTER_FIELDS = ["product__title", "product__shop__title", "product__category__title"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
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
                    "product__created_at",
                    "product__photos",
                    "product__category__categoryId",
                    "product__category__title",
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
    VALID_FILTER_FIELDS = ["product__title", "product__shop__title", "product__category__title"]

    @extend_schema(tags=["Product"])
    def get(self, request: Request):
        try:
            print("Start GrowingProductsView")
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
                    "product__created_at",
                    "product__photos",
                    "product__category__categoryId",
                    "product__category__title",
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
