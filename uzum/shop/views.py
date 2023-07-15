import math
import time
import traceback
from datetime import datetime, timedelta

import pytz
from django.db import connection
from django.db.models import Count, F, Q, Max, Min, OuterRef, Subquery, Sum, IntegerField, CharField
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.generics import ListAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.exceptions import ValidationError
from uzum.category.models import Category, CategoryAnalytics
from uzum.category.pagination import CategoryProductsPagination
from uzum.category.serializers import ProductAnalyticsViewSerializer
from uzum.product.models import Product, ProductAnalytics, ProductAnalyticsView
from uzum.product.serializers import ProductAnalyticsSerializer, ProductSerializer
from uzum.review.views import CookieJWTAuthentication
from uzum.shop.models import Shop, ShopAnalytics
from uzum.sku.models import SkuAnalytics
from uzum.utils.general import get_day_before_pretty, get_next_day_pretty, get_today_pretty, get_today_pretty_fake

from .serializers import ExtendedShopSerializer, ShopAnalyticsSerializer, ShopCompetitorsSerializer, ShopSerializer


def get_totals(date_pretty):
    totals = ShopAnalytics.objects.filter(date_pretty=date_pretty).aggregate(
        total_orders=Sum("total_orders"),
        total_products=Sum("total_products"),
        total_reviews=Sum("total_reviews"),
    )
    return totals


class Top5ShopsView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ShopSerializer
    queryset = Shop.objects.all()
    allowed_methods = ["GET"]

    @extend_schema(tags=["Shop"])
    def get(self, request: Request):
        try:
            date_pretty = get_today_pretty_fake()
            shops = (
                ShopAnalytics.objects.filter(date_pretty=date_pretty)
                .order_by("-total_orders")[:5]
                .values("shop__title", "total_orders")
            )

            return Response(shops, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class CurrentShopView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Shop"])
    def get(self, request: Request, link: str):
        try:
            shop = Shop.objects.get(link=link)
            serializer = ShopSerializer(shop)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class TreemapShopsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Shop"])
    def get(self, request: Request):
        try:
            shops = (
                ShopAnalytics.objects.filter(date_pretty=get_today_pretty_fake())
                .order_by("-total_products")
                .values("shop__title", "shop__link", "total_orders", "total_products", "total_reviews")
            )

            totals = get_totals(get_today_pretty_fake())

            return Response(
                data={
                    "data": {
                        "total_orders": totals["total_orders"],
                        "total_products": totals["total_products"],
                        "total_reviews": totals["total_reviews"],
                        "shops": shops,
                    }
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ShopsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    PAGE_SIZE = 20
    VALID_COLUMNS = [
        "position",
        "total_products",
        "total_orders",
        "total_reviews",
        "average_purchase_price",
        "average_order_price",
        "rating",
        "num_categories",
    ]
    VALID_ORDERS = ["asc", "desc"]
    VALID_SEARCHES = ["shop_title"]

    def get(self, request: Request, *args, **kwargs):
        try:
            date_pretty = get_today_pretty_fake()
            page_number = int(request.query_params.get("page", 1))
            offset = (page_number - 1) * self.PAGE_SIZE
            column = request.query_params.get("column", "position")
            order = request.query_params.get("order", "asc")

            search_columns = request.query_params.get("searches", "")
            searches_dict = {}

            if search_columns:
                filters = request.query_params.get("filters", "")

                searchs = search_columns.split(",")

                for col in searchs:
                    if col not in self.VALID_SEARCHES:
                        return Response({"error": f"Invalid search column: {col}"}, status=status.HTTP_400_BAD_REQUEST)

                if len(searchs) == 0 or len(searchs) > 1:
                    return Response({"error": "Invalid search columns"}, status=status.HTTP_400_BAD_REQUEST)
                searchs[0] = "s.title"

                filters = filters.split(",")

                for i in range(len(searchs)):
                    searches_dict[searchs[i]] = filters[i]

            if column not in self.VALID_COLUMNS:
                return Response({"error": f"Invalid column: {column}"}, status=status.HTTP_400_BAD_REQUEST)
            if order not in self.VALID_ORDERS:
                return Response({"error": f"Invalid order: {order}"}, status=status.HTTP_400_BAD_REQUEST)

            with connection.cursor() as cursor:
                # Construct search clause
                search_clause = ""
                if searches_dict:
                    for key, value in searches_dict.items():
                        if search_clause:
                            search_clause += " AND "
                        search_clause += f"LOWER({key}) LIKE LOWER('%%{value}%%')"
                    search_clause = " AND " + search_clause

                # First, count total number of rows
                cursor.execute(
                    """
                    SELECT COUNT(*)
                    FROM shop_shopanalytics sa
                    JOIN shop_shop s ON sa.shop_id = s.seller_id
                    WHERE sa.date_pretty = %s
                """,
                    [date_pretty],
                )
                total_count = cursor.fetchone()[0]
                total_pages = -(-total_count // self.PAGE_SIZE)  # Equivalent to math.ceil(total_count / page_size)

                # Then fetch the data
                cursor.execute(
                    f"""
                    SELECT sa.id, sa.total_products, sa.total_orders, sa.total_reviews,
                        sa.average_purchase_price, sa.average_order_price, sa.rating,
                        sa.date_pretty,
                        COUNT(DISTINCT sac.category_id) as num_categories,
                        s.title as shop_title, s.link as seller_link,
                        ROW_NUMBER() OVER (ORDER BY sa.total_orders DESC) as position
                    FROM shop_shopanalytics sa
                    JOIN shop_shop s ON sa.shop_id = s.seller_id
                    LEFT JOIN shop_shopanalytics_categories sac ON sa.id = sac.shopanalytics_id
                    WHERE sa.date_pretty = %s {search_clause}
                    GROUP BY sa.id, s.title, s.link
                    ORDER BY {column} {order}
                    LIMIT %s OFFSET %s
                """,
                    [date_pretty, self.PAGE_SIZE, offset],
                )
                columns = [col[0] for col in cursor.description]
                results = [dict(zip(columns, row)) for row in cursor.fetchall()]

                # attach shop link to title as title(link)
                for result in results:
                    result["shop_title"] = f'{result["shop_title"]}(({result["seller_link"]}))'

            # Create the response data
            data = {
                "results": results,
                "count": total_count,
            }

            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ShopsOrdersSegmentationView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ShopSerializer
    queryset = Shop.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @staticmethod
    def shops_segmentation(request: Request, start_date, segments_count=15):
        # Annotate each shop with the number of orders they received from start_date to now

        # Define subqueries for total orders at start_date and now
        start_date_orders = (
            ShopAnalytics.objects.filter(shop=OuterRef("pk"), created_at__date__gte=start_date)
            .order_by("created_at")
            .values("total_orders")[:1]
        )

        current_orders = (
            ShopAnalytics.objects.filter(shop=OuterRef("pk"), created_at__date__lte=timezone.now().date())
            .order_by("-created_at")
            .values("total_orders")[:1]
        )

        latest_shop_analytics = ShopAnalytics.objects.filter(shop=OuterRef("pk")).order_by("-created_at")

        # Annotate each shop with total_orders at start_date and now
        shops = Shop.objects.annotate(
            start_date_orders=Subquery(start_date_orders),
            current_orders=Subquery(current_orders),
            total_orders=Subquery(latest_shop_analytics.values("total_orders")[:1]),
            total_products=Subquery(latest_shop_analytics.values("total_products")[:1]),
            total_reviews=Subquery(latest_shop_analytics.values("total_reviews")[:1]),
            rating=Subquery(latest_shop_analytics.values("rating")[:1]),
            date_pretty=Subquery(latest_shop_analytics.values("date_pretty")[:1]),
        )

        # Calculate the difference in total orders
        shops = shops.annotate(order_difference=F("current_orders") - F("start_date_orders"))

        # Get min and max of order_difference for binning
        min_orders = shops.aggregate(Min("order_difference"))["order_difference__min"]
        max_orders = shops.aggregate(Max("order_difference"))["order_difference__max"]

        if min_orders < 0:
            min_orders = 0

        # Create 15 bins based on min_orders and max_orders
        step = (max_orders - min_orders) / segments_count

        segments = []

        # Create segments
        for i in range(segments_count):
            from_value = min_orders + (i * step)
            to_value = min_orders + ((i + 1) * step)
            segment_shops = shops.filter(order_difference__gte=from_value, order_difference__lt=to_value)

            segments.append(
                {"from": from_value, "to": to_value, "shops": ExtendedShopSerializer(segment_shops, many=True).data}
            )

        return segments

    @extend_schema(tags=["Shop"])
    def get(self, request: Request):
        try:
            start_date_str = request.query_params.get(
                "start_date", (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")  # default 30 days ago
            )
            start_date = timezone.make_aware(
                datetime.strptime(start_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            )

            segments = self.shops_segmentation(request, start_date=start_date)

            return Response(data={"data": segments}, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ShopsProductsSegmentation(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ShopSerializer
    queryset = Shop.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @staticmethod
    def shops_segmentation(request: Request, segments_count=15):
        # Annotate each shop with the number of orders they received from start_date to now

        current_products = (
            ShopAnalytics.objects.filter(shop=OuterRef("pk"), created_at__date__lte=timezone.now().date())
            .order_by("-created_at")
            .values("total_products")[:1]
        )

        latest_shop_analytics = ShopAnalytics.objects.filter(shop=OuterRef("pk")).order_by("-created_at")

        # Annotate each shop with total_orders at start_date and now
        shops = Shop.objects.annotate(
            total_products=Subquery(current_products),
            date_pretty=Subquery(latest_shop_analytics.values("date_pretty")[:1]),
        )

        for shop in shops:
            if shop.total_products > 4000:
                print(shop.title, shop.total_products)

        # Get min and max of order_difference for binning
        min_products = shops.aggregate(Min("total_products"))["total_products__min"]
        max_products = shops.aggregate(Max("total_products"))["total_products__max"]

        # Create 15 bins based on min_orders and max_orders
        step = math.ceil((max_products - min_products) / segments_count)

        segments = []

        # Create segments
        for i in range(segments_count):
            from_value = min_products + (i * step)
            to_value = min_products + ((i + 1) * step)
            segment_shops = shops.filter(total_products__gte=from_value, total_products__lt=to_value)

            segments.append(
                {
                    "from": from_value,
                    "to": to_value,
                    "shops": [
                        {
                            "name": shop.title,
                            "created_at": shop.created_at,
                            "total_products": shop.total_products,
                        }
                        for shop in segment_shops
                    ],
                }
            )

        return segments

    @extend_schema(tags=["Shop"])
    def get(self, request: Request):
        try:
            segments = self.shops_segmentation(request)

            return Response(data={"data": segments}, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ShopAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ShopAnalyticsSerializer
    queryset = Shop.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @extend_schema(tags=["Shop"])
    def get(self, request: Request, seller_id: int):
        try:
            range = request.query_params.get("range", 15)
            start = time.time()
            # get start_date 00:00 in Asia/Tashkent timezone which is range days ago
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=int(range) + 1), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            if datetime.now().astimezone(pytz.timezone("Asia/Tashkent")).hour < 7:
                # end date is end of yesterday
                end_date = timezone.make_aware(
                    datetime.now() - timedelta(days=1), timezone=pytz.timezone("Asia/Tashkent")
                ).replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                # end date is end of today
                end_date = timezone.make_aware(datetime.now(), timezone=pytz.timezone("Asia/Tashkent")).replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

            if seller_id is None:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sa.id, sa.total_products, sa.total_orders, sa.total_reviews,
                        sa.average_purchase_price, sa.average_order_price, sa.rating, sa.position,
                        sa.date_pretty, COUNT(sa_categories.category_id) as category_count
                    FROM shop_shopanalytics sa
                    LEFT JOIN shop_shopanalytics_categories sa_categories ON sa.id = sa_categories.shopanalytics_id
                    WHERE sa.created_at >= %s AND sa.shop_id = %s AND sa.created_at <= %s
                    GROUP BY sa.id
                    ORDER BY sa.created_at ASC
                    """,
                    [start_date, seller_id, end_date],
                )
                columns = [col[0] for col in cursor.description]
                data = [dict(zip(columns, row)) for row in cursor.fetchall()]
            return Response(data, status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class ShopCompetitorsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ShopCompetitorsSerializer
    queryset = Shop.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    def get_competitor_shops(self, shop: Shop, N=10):
        try:
            date_pretty = get_today_pretty_fake()
            # Get the shop analytics of the current shop for today's date
            shop_analytics_today = ShopAnalytics.objects.get(shop=shop, date_pretty=date_pretty)

            # Get the ids of all categories for the shop
            shop_categories_ids = shop_analytics_today.categories.values_list("categoryId", flat=True)

            # Convert to a list of string to be used in raw SQL query
            shop_categories_ids_str = ",".join(map(str, shop_categories_ids))

            # Get current shop's average purchase price and position
            current_shop_avg_purchase_price = shop_analytics_today.average_purchase_price
            current_shop_position = shop_analytics_today.position

            query = f"""
                SELECT
                    sa.shop_id, s.title, s.link, COUNT(DISTINCT sac.category_id) as common_categories_count,
                    sa.average_purchase_price, sa.position,
                    ABS(sa.average_purchase_price - {current_shop_avg_purchase_price}) as price_difference,
                    ABS(sa.position - {current_shop_position}) as position_difference,
                    STRING_AGG(DISTINCT c.title, ', ') as common_categories_titles
                FROM
                    shop_shopanalytics as sa
                JOIN
                    shop_shopanalytics_categories as sac on sa.id = sac.shopanalytics_id
                JOIN
                    shop_shop as s on sa.shop_id = s.seller_id
                JOIN
                    category_category as c on sac.category_id = c."categoryId"
                WHERE
                    sa.date_pretty = '{date_pretty}'
                    AND sac.category_id IN ({shop_categories_ids_str})
                GROUP BY
                    sa.shop_id, s.title, s.link, sa.average_purchase_price, sa.position
                ORDER BY
                    sa.shop_id != {shop.seller_id},  -- prioritize the current shop
                    common_categories_count DESC,
                    price_difference ASC,
                    position_difference ASC
                LIMIT {N + 1}  -- increase the limit to include the current shop
            """

            with connection.cursor() as cursor:
                cursor.execute(query)
                competitor_shops_data = cursor.fetchall()

            return competitor_shops_data
        except Exception as e:
            print(e)
            traceback.print_exc()
            return []

    @extend_schema(tags=["Shop"])
    def get(self, request: Request, seller_id: int):
        try:
            if seller_id is None:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            print("Shop Competitors View")
            start = time.time()
            shop = get_object_or_404(Shop, seller_id=seller_id)
            range = request.query_params.get("range", 15)
            print(shop.title)
            # get start_date 00:00 in Asia/Tashkent timezone which is range days ago
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=int(range) + 1), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            # check if it is before 7 am in Tashkent
            if datetime.now().astimezone(pytz.timezone("Asia/Tashkent")).hour < 7:
                # end date is end of yesterday
                end_date = timezone.make_aware(
                    datetime.now() - timedelta(days=1), timezone=pytz.timezone("Asia/Tashkent")
                ).replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                # end date is end of today
                end_date = timezone.make_aware(datetime.now(), timezone=pytz.timezone("Asia/Tashkent")).replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

            competitor_shops_data = self.get_competitor_shops(shop)

            competitors_ids = [data[0] for data in competitor_shops_data]

            competitors_analytics = (
                ShopAnalytics.objects.filter(
                    shop__seller_id__in=competitors_ids, created_at__range=[start_date, end_date]
                )
                .annotate(category_count=Count("categories"))
                .values(
                    "id",
                    "total_products",
                    "total_orders",
                    "total_reviews",
                    "average_purchase_price",
                    "average_order_price",
                    "rating",
                    "position",
                    "date_pretty",
                    "category_count",
                    "shop__seller_id",
                )
            )

            # preparing a dict for easy lookup
            competitors_analytics_dict = {}
            for analytics in competitors_analytics:
                competitor_id = analytics.pop("shop__seller_id")
                if competitor_id in competitors_analytics_dict:
                    competitors_analytics_dict[competitor_id].append(analytics)
                else:
                    competitors_analytics_dict[competitor_id] = [analytics]

            competitors_data = []
            for (
                shop_id,
                title,
                link,
                common_categories_count,
                avg_purchase_price,
                position,
                price_difference,
                position_difference,
                common_categories_titles,
            ) in competitor_shops_data:
                competitors_data.append(
                    {
                        "title": title,
                        "link": link,
                        "common_categories_count": common_categories_count,
                        "common_categories_titles": common_categories_titles.split(","),
                        "analytics": competitors_analytics_dict.get(shop_id, []),
                    }
                )

            # Get shop's own analytics
            shop_analytics = (
                ShopAnalytics.objects.filter(shop=shop, created_at__gte=start_date)
                .annotate(category_count=Count("categories"))
                .values(
                    "id",
                    "total_products",
                    "total_orders",
                    "total_reviews",
                    "average_purchase_price",
                    "average_order_price",
                    "rating",
                    "position",
                    "date_pretty",
                    "category_count",
                )
            )
            shop_analytics_data = list(shop_analytics)

            print(f"Time taken Competitors: {time.time() - start}")
            return Response(data={"data": competitors_data, "shop": shop_analytics_data}, status=status.HTTP_200_OK)
        except Shop.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Shop not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


class ShopDailySalesView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request: Request, seller_id: int):
        """
        Get Productanalytics of a shop at a specific date and next day
        """
        try:
            #! TODO: some products are not showing up in the analytics
            print("Shop Daily Sales View")
            start = time.time()
            shop = get_object_or_404(Shop, seller_id=seller_id)

            today_pretty = get_today_pretty_fake()
            date = request.query_params.get("date", None)

            if not date:
                date = today_pretty
            else:
                date = get_next_day_pretty(date)

            start_date = timezone.make_aware(
                datetime.strptime(date, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            def calculate_diff(target, before):
                """
                Helper function to calculate the difference between the target and before value.
                """
                if target is not None and before is not None:
                    return target - before
                return target

            analytics_date = (
                ProductAnalytics.objects.filter(date_pretty=date, product__shop=shop)
                .values(
                    "average_purchase_price",
                    "orders_amount",
                    "position",
                    "position_in_category",
                    "position_in_shop",
                    "available_amount",
                    "reviews_amount",
                    "rating",
                    "product__title",
                    "product__category__title",
                    "product__product_id",
                    "product__photos",
                    "date_pretty",
                )
                .order_by("-orders_amount")
            )

            latest_date_subquery = (
                ProductAnalytics.objects.filter(
                    product__shop=shop, created_at__lt=start_date, product_id=OuterRef("product_id")
                )
                .order_by("-created_at")
                .values("date_pretty")[:1]
            )

            day_before_analytics = ProductAnalytics.objects.filter(
                product__shop=shop, date_pretty=Subquery(latest_date_subquery)
            ).values(
                "average_purchase_price",
                "orders_amount",
                "position",
                "position_in_category",
                "position_in_shop",
                "available_amount",
                "reviews_amount",
                "rating",
                "product__title",
                "product__category__title",
                "product__product_id",
                "date_pretty",
            )

            target_analytics = list(analytics_date)

            before_analytics_dict = {i["product__product_id"]: i for i in day_before_analytics}

            print("before date_pretty", day_before_analytics[0]["date_pretty"])
            for item in target_analytics:
                before_item = before_analytics_dict.get(item["product__product_id"], None)
                item["product__title"] += f'(({item["product__product_id"]}))'
                item["product__category__title"] += f'(({item["product__product_id"]}))'

                item["orders"] = {
                    "target": item["orders_amount"],
                    # "before": before_item["orders_amount"],
                    "before": before_item.get("orders_amount", None) if before_item else None,
                    "change": calculate_diff(item["orders_amount"], before_item["orders_amount"])
                    if before_item
                    else item["orders_amount"],
                }
                item["reviews"] = {
                    "target": item["reviews_amount"],
                    # "before": before_item["reviews_amount"],
                    "before": before_item.get("reviews_amount", None) if before_item else None,
                    "change": calculate_diff(item["reviews_amount"], before_item["reviews_amount"])
                    if before_item
                    else item["reviews_amount"],
                }

                item["rating"] = {
                    "target": item["rating"],
                    # "before": before_item["rating"],
                    "before": before_item.get("rating", None) if before_item else None,
                    "change": calculate_diff(item["rating"], before_item["rating"]) if before_item else item["rating"],
                }

                item["position"] = {
                    "target": item["position"],
                    # "before": before_item["position"],
                    "before": before_item.get("position", None) if before_item else None,
                    "change": calculate_diff(item["position"], before_item["position"])
                    if before_item
                    else item["position"],
                }

                item["position_in_category"] = {
                    "target": item["position_in_category"],
                    # "before": before_item["position_in_category"],
                    "before": before_item.get("position_in_category", None) if before_item else None,
                    "change": calculate_diff(item["position_in_category"], before_item["position_in_category"])
                    if before_item
                    else item["position_in_category"],
                }

                item["position_in_shop"] = {
                    "target": item["position_in_shop"],
                    # "before": before_item["position_in_shop"],
                    "before": before_item.get("position_in_shop", None) if before_item else None,
                    "change": calculate_diff(item["position_in_shop"], before_item["position_in_shop"])
                    if before_item
                    else item["position_in_shop"],
                }

                item["available_amount"] = {
                    "target": item["available_amount"],
                    # "before": before_item["available_amount"],
                    "before": before_item.get("available_amount", None) if before_item else None,
                    "change": calculate_diff(item["available_amount"], before_item["available_amount"])
                    if before_item
                    else item["available_amount"],
                }

                item["average_purchase_price"] = {
                    "target": item["average_purchase_price"],
                    # "before": before_item["average_purchase_price"],
                    "before": before_item.get("average_purchase_price", None) if before_item else None,
                    "change": calculate_diff(item["average_purchase_price"], before_item["average_purchase_price"])
                    if before_item
                    else item["average_purchase_price"],
                }

            if len(target_analytics) > 300:
                final_res = [
                    entry
                    for entry in target_analytics
                    if entry["average_purchase_price"]["change"] != 0
                    or (entry["orders"]["change"] != 0 and entry["orders"]["change"] is not None)
                    or (entry["reviews"]["change"] != 0 and entry["reviews"]["change"] is not None)
                    or (entry["rating"]["change"] != 0 and entry["rating"]["change"] is not None)
                    or (entry["available_amount"]["change"] != 0 and entry["available_amount"]["change"] is not None)
                ]
            else:
                final_res = target_analytics

            print("Shop Daily Sales View Time taken: ", time.time() - start)

            return Response(
                final_res,
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


class ShopProductsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ProductAnalyticsViewSerializer
    pagination_class = CategoryProductsPagination
    VALID_FILTER_FIELDS = ["category_title", "product_title"]

    def get_queryset(self):
        """
        This view should return a list of all the products for
        the category as determined by the category portion of the URL.
        """
        seller_id = self.kwargs["seller_id"]

        shop = get_object_or_404(Shop, seller_id=seller_id)

        ordering = self.request.query_params.get("order", "desc")
        column = self.request.query_params.get("column", "orders_amount")
        search_columns = self.request.query_params.get("searches", "")  # default is empty string
        filters = self.request.query_params.get("filters", "")  # default is empty string

        # Build filter query
        filter_query = Q()
        if search_columns and filters:
            search_columns = search_columns.split(",")
            filters = filters.split("---")

            if len(search_columns) != len(filters):
                raise ValidationError({"error": "Invalid search query"})

            for i in range(len(search_columns)):
                if search_columns[i] not in self.VALID_FILTER_FIELDS:
                    raise ValidationError({"error": f"Invalid search column: {search_columns[i]}"})

                # filter_query |= Q(**{f"{search_columns[i]}__icontains": filters[i]})
                # it should be And not Or and case insensitive
                filter_query &= Q(**{f"{search_columns[i]}__icontains": filters[i]})

        order_by_column = column
        if ordering == "desc":
            order_by_column = f"-{column}"

        return ProductAnalyticsView.objects.filter(shop_link=shop.link).filter(filter_query).order_by(order_by_column)

    def list(self, request, *args, **kwargs):
        start_time = time.time()
        print("Shop PRODUCTS")
        response = super().list(request, *args, **kwargs)
        print(f"Shop PRODUCTS: {time.time() - start_time} seconds")
        return response


class ShopTopProductsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ProductAnalyticsViewSerializer

    def get(self, request: Request, seller_id: int):
        """
        This view should return a list of all the products for
        the category as determined by the category portion of the URL.
        """
        seller_id = self.kwargs["seller_id"]
        shop = Shop.objects.get(seller_id=seller_id)

        latest_analytics = ShopAnalytics.objects.filter(shop=shop).order_by("-created_at")[0]
        products = ProductAnalyticsView.objects.filter(shop_link=shop.link)

        n = 10 if products.count() < 100 else 20

        orders_products = products.order_by("-orders_amount")[:n]
        reviews_products = products.order_by("-reviews_amount")[:n]

        return Response(
            data={
                "orders_products": ProductAnalyticsViewSerializer(orders_products, many=True).data,
                "reviews_products": ProductAnalyticsViewSerializer(reviews_products, many=True).data,
                "total_orders": latest_analytics.total_orders,
                "total_reviews": latest_analytics.total_reviews,
            },
            status=status.HTTP_200_OK,
        )


class StoppedProductsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    # pagination_class = PageNumberPagination
    serializer_class = ProductAnalyticsSerializer

    @extend_schema(tags=["Product"])
    def get(self, request: Request, seller_id: int):
        try:
            # Write the raw SQL query
            print("STOPPED PRODUCTS")
            start = time.time()
            query = f"""
            SELECT p.title, p.photos, pa.*, c.title AS category_title, c."categoryId" as category_id,  AVG(ska.purchase_price) AS avg_purchase_price, AVG(ska.full_price) AS avg_full_price
            FROM product_product p
            INNER JOIN category_category c ON p.category_id = c."categoryId"
            INNER JOIN (
                SELECT pa_inner.*
                FROM product_productanalytics pa_inner
                WHERE pa_inner.created_at IN (
                    SELECT MAX(pa2.created_at)
                    FROM product_productanalytics pa2
                    WHERE pa2.product_id = pa_inner.product_id
                ) AND pa_inner.created_at <= NOW() - INTERVAL '2 days'
            ) pa ON p.product_id = pa.product_id
            LEFT JOIN sku_sku s ON p.product_id = s.product_id
            LEFT JOIN sku_skuanalytics ska ON s.sku = ska.sku_id AND pa.date_pretty = ska.date_pretty
            WHERE p.shop_id = {seller_id}
            GROUP BY p.title, pa.id, c.title, c."categoryId", p.photos, pa.created_at, pa.date_pretty, pa.product_id, pa.reviews_amount, pa.orders_amount, pa.rating, pa.available_amount, pa.orders_money, pa.position, pa.position_in_category, pa.position_in_shop, pa.average_purchase_price
            """

            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                print(f"STOPPED PRODUCTS ROWS: {time.time() - start} seconds")
                # Fetch the column names from the cursor description
                column_names = [column[0] for column in cursor.description]

                # Convert the rows into a list of dictionaries
                result = [dict(zip(column_names, row)) for row in rows]

            for row in result:
                row["title"] = row["title"] + f'(({row["product_id"]}))'
                row["category_title"] = row["category_title"] + f'(({row["category_id"]}))'

            print(f"STOPPED PRODUCTS: {time.time() - start} seconds")
            return Response(data=result, status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


class ShopCategoriesView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Shop"])
    def get(self, request: Request, seller_id: int):
        """
        For each category shop has, return the category title, id, and the number of products in that category, number of orders, and number of reviews.
        Args:
            request (Request): _description_
            seller_id (int): _description_
        Returns:
            _type_: _description_
        """
        try:
            print("SHOP CATEGORIES")
            start = time.time()
            query = f"""
            SELECT c."categoryId", c.title, COUNT(p.product_id) AS products_amount, SUM(pa.orders_amount) AS orders_amount, SUM(pa.reviews_amount) AS reviews_amount
            FROM category_category c
            INNER JOIN product_product p ON c."categoryId" = p.category_id
            INNER JOIN (
                SELECT pa_inner.*
                FROM product_productanalytics pa_inner
                WHERE pa_inner.created_at IN (
                    SELECT MAX(pa2.created_at)
                    FROM product_productanalytics pa2
                    WHERE pa2.product_id = pa_inner.product_id
                )
            ) pa ON p.product_id = pa.product_id
            WHERE p.shop_id = {seller_id}
            GROUP BY c."categoryId", c.title
            ORDER BY products_amount DESC
            """

            with connection.cursor() as cursor:
                cursor.execute(query)
                rows = cursor.fetchall()
                print(f"SHOP CATEGORIES ROWS: {time.time() - start} seconds")
                # Fetch the column names from the cursor description
                column_names = [column[0] for column in cursor.description]

                # Convert the rows into a list of dictionaries
                result = [dict(zip(column_names, row)) for row in rows]
            print(f"SHOP CATEGORIES: {time.time() - start} seconds")
            return Response(data=result, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


class ShopCategoryAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Shop"])
    def get(self, request: Request, seller_id: int, category_id: int):
        if seller_id is None or category_id is None:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            start = time.time()
            print("SHOP CATEGORY ANALYTICS")
            range_ = int(request.query_params.get("range", 15))
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=range_), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=23, minute=59, second=59, microsecond=999999)

            # if it is before 7 am in Tashkent, it is still yesterday
            if datetime.now().astimezone(pytz.timezone("Asia/Tashkent")).hour < 7:
                current_date = timezone.make_aware(
                    datetime.now() - timedelta(days=1), timezone=pytz.timezone("Asia/Tashkent")
                ).replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                current_date = timezone.make_aware(datetime.now(), timezone=pytz.timezone("Asia/Tashkent")).replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

            dates = [start_date + timedelta(days=i) for i in range((current_date - start_date).days + 1)]

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    WITH date_range AS (
                        SELECT generate_series(%s, %s, interval '1 day')::date AS date
                    ),
                    product_list AS (
                        SELECT product_id
                        FROM product_product
                        WHERE shop_id = %s AND category_id = %s
                    ),
                    latest_analytics AS (
                        SELECT
                            pa.product_id,
                            pa.orders_amount,
                            pa.reviews_amount,
                            dr.date,
                            ROW_NUMBER() OVER (
                                PARTITION BY pa.product_id, dr.date
                                ORDER BY pa.date_pretty::date DESC
                            ) AS row_number
                        FROM product_productanalytics AS pa
                        JOIN product_list AS pl ON pa.product_id = pl.product_id
                        JOIN date_range AS dr ON pa.date_pretty::date <= dr.date
                    ),
                    aggregated_analytics AS (
                        SELECT
                            la.date,
                            SUM(la.orders_amount) AS total_orders,
                            SUM(la.reviews_amount) AS total_reviews,
                            COUNT(*) FILTER (WHERE la.row_number = 1) AS total_products
                        FROM latest_analytics AS la
                        WHERE la.row_number = 1
                        GROUP BY la.date
                    )
                    SELECT
                        aa.date,
                        aa.total_orders,
                        aa.total_reviews,
                        aa.total_products
                    FROM aggregated_analytics AS aa
                    ORDER BY aa.date
                """,
                    [start_date, current_date, seller_id, category_id],
                )

                res = [
                    {
                        "category_id": category_id,
                        "date": date,
                        "data": {
                            "orders_amount": total_orders,
                            "products_count": total_products,
                            "reviews_amount": total_reviews,
                        },
                    }
                    for date, total_orders, total_reviews, total_products in cursor.fetchall()
                ]

            print(f"SHOP CATEGORY ANALYTICS: {time.time() - start} seconds")
            return Response(data=res, status=status.HTTP_200_OK)

        except Shop.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"detail": "Shop not found."})

        except Exception as e:
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"detail": str(e)})


class ShopProductsByCategoryView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [CookieJWTAuthentication]
    serializer_class = ProductSerializer
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @extend_schema(tags=["Shop"])
    def get(self, request: Request, seller_id: int, category_id: int):
        if seller_id is None or category_id is None:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            shop = Shop.objects.get(pk=seller_id)
            category = Category.objects.get(pk=category_id)

            categories = Category.get_descendants(category, include_self=True)
            latest_product_analytics_orders_amount = Subquery(
                ProductAnalytics.objects.filter(product__product_id=OuterRef("product_id"))
                .order_by("-date_pretty")
                .values("orders_amount")[:1],
                output_field=IntegerField(),
            )

            latest_product_analytics_reviews_amount = Subquery(
                ProductAnalytics.objects.filter(product__product_id=OuterRef("product_id"))
                .order_by("-date_pretty")
                .values("reviews_amount")[:1],
                output_field=IntegerField(),
            )

            latest_product_analytics_available_amount = Subquery(
                ProductAnalytics.objects.filter(product__product_id=OuterRef("product_id"))
                .order_by("-date_pretty")
                .values("reviews_amount")[:1],
                output_field=IntegerField(),
            )

            latest_product_analytics_date = Subquery(
                ProductAnalytics.objects.filter(product__product_id=OuterRef("product_id"))
                .order_by("-date_pretty")
                .values("date_pretty")[:1],
                output_field=CharField(),
            )

            products = (
                Product.objects.filter(shop=shop, category__in=categories)
                .values(
                    "product_id",
                    "title",
                    "photos",
                )
                .annotate(
                    latest_product_analytics_date=latest_product_analytics_date,
                    latest_product_analytics_orders_amount=latest_product_analytics_orders_amount,
                    latest_product_analytics_reviews_amount=latest_product_analytics_reviews_amount,
                    latest_product_analytics_available_amount=latest_product_analytics_available_amount,
                )
            )

            for product in products:
                product["title"] = product["title"] + f'(({product["product_id"]}))'

            return Response(
                data={"data": products, "total": len(products)},
                status=status.HTTP_200_OK,
            )
        except Shop.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Shop not found"})
        except Category.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Category not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


class UzumTotalOrders(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request):
        """
        For everyday, sum all orders in all shopanalytics
        Args:
            request (_type_): _description_

        Returns:
            _type_: _description_
        """
        try:
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=45), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            if datetime.now().astimezone(pytz.timezone("Asia/Tashkent")).hour < 7:
                # end date is end of yesterday
                end_date = timezone.make_aware(
                    datetime.now() - timedelta(days=1), timezone=pytz.timezone("Asia/Tashkent")
                ).replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                # end date is end of today
                end_date = timezone.make_aware(datetime.now(), timezone=pytz.timezone("Asia/Tashkent")).replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )

            # Group by date_pretty and calculate the sum of total_orders for each day
            data = (
                ShopAnalytics.objects.filter(created_at__range=[start_date, end_date])
                .values("date_pretty")
                .annotate(total_orders=Sum("total_orders"))
                .order_by("date_pretty")
            )

            return Response(list(data), status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UzumTotalProducts(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request):
        try:
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=45), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            if datetime.now().astimezone(pytz.timezone("Asia/Tashkent")).hour < 7:
                # end date is end of yesterday
                end_date = timezone.make_aware(
                    datetime.now() - timedelta(days=1), timezone=pytz.timezone("Asia/Tashkent")
                ).replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                # end date is end of today
                end_date = timezone.make_aware(datetime.now(), timezone=pytz.timezone("Asia/Tashkent")).replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
            product_analytics = ProductAnalytics.objects.filter(created_at__range=[start_date, end_date])
            daily_totals = (
                product_analytics.values("date_pretty")
                .annotate(total_products=Count("product__product_id"))
                .values("date_pretty", "total_products")
                .order_by("date_pretty")
            )
            return Response(daily_totals, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class UzumTotalShops(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request):
        try:
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=45), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            if datetime.now().astimezone(pytz.timezone("Asia/Tashkent")).hour < 7:
                # end date is end of yesterday
                end_date = timezone.make_aware(
                    datetime.now() - timedelta(days=1), timezone=pytz.timezone("Asia/Tashkent")
                ).replace(hour=23, minute=59, second=59, microsecond=999999)
            else:
                # end date is end of today
                end_date = timezone.make_aware(datetime.now(), timezone=pytz.timezone("Asia/Tashkent")).replace(
                    hour=23, minute=59, second=59, microsecond=999999
                )
            product_analytics = ShopAnalytics.objects.filter(created_at__range=[start_date, end_date])
            daily_totals = (
                product_analytics.values("date_pretty")
                .annotate(total_shops=Count("shop__seller_id"))
                .values("date_pretty", "total_shops")
                .order_by("date_pretty")
            )
            return Response(daily_totals, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
