import io
import math
import time
import traceback
from datetime import datetime, timedelta

import pytz
from django.db import connection
from django.db.models import (CharField, Count, F, IntegerField, Max, Min,
                              OuterRef, Q, Subquery, Sum)
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
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

from uzum.category.models import Category
from uzum.category.pagination import CategoryProductsPagination
from uzum.category.serializers import ProductAnalyticsViewSerializer
from uzum.product.models import Product, ProductAnalytics, ProductAnalyticsView
from uzum.product.serializers import (ProductAnalyticsSerializer,
                                      ProductSerializer)
from uzum.review.views import CookieJWTAuthentication
from uzum.shop.models import (Shop, ShopAnalytics, ShopAnalyticsRecent,
                              ShopAnalyticsTable)
from uzum.users.models import User
from uzum.utils.general import (Tariffs, authorize_Base_tariff,
                                get_day_before_pretty,
                                get_days_based_on_tariff, get_next_day_pretty,
                                get_today_pretty_fake)

from .serializers import (ExtendedShopSerializer,
                          ShopAnalyticsRecentExcelSerializer,
                          ShopAnalyticsRecentSerializer,
                          ShopAnalyticsSerializer, ShopCompetitorsSerializer,
                          ShopSerializer)


def get_totals(date_pretty):
    totals = ShopAnalytics.objects.filter(date_pretty=date_pretty).aggregate(
        total_orders=Sum("total_orders"),
        total_products=Sum("total_products"),
        total_reviews=Sum("total_reviews"),
    )
    return totals


class SearchEverythingView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request: Request, *args, **kwargs):
        try:
            authorize_Base_tariff(request)
            search = request.query_params.get("search", "")
            isProductsSelected = request.query_params.get("isProductSelected", False)
            isShopsSelected = request.query_params.get("isStoreSelected", False)
            isCategoriesSelected = request.query_params.get("isCategorySelected", False)
            lang = request.query_params.get("lang", "ru")

            isRu = lang == "ru"

            if not search or len(search) < 3:
                return Response(status=201, data={"products": [], "shops": [], "categories": []})

            products = []
            products_count = 0
            shops = []
            shops_count = 0
            categories = []
            categories_count = 0

            # print(search, isProductsSelected, isShopsSelected, isCategoriesSelected, lang)

            if isProductsSelected == "true":
                if isRu:
                    products = ProductAnalyticsView.objects.filter(product_title_ru__icontains=search).values(
                        "product_title_ru", "product_title", "product_id", "photos", "shop_title", "shop_link"
                    )
                else:
                    products = ProductAnalyticsView.objects.filter(product_title__icontains=search).values(
                        "product_title", "product_title_ru", "product_id", "photos", "shop_title", "shop_link"
                    )

                products_count = products.count()

                if products_count > 100:
                    products = products[:100]

            if isShopsSelected == "true":
                shops = Shop.objects.filter(title__icontains=search).values("title", "link")
                shops_count = shops.count()

                if shops_count > 100:
                    shops = shops[:100]

            if isCategoriesSelected == "true":
                if isRu:
                    categories = Category.objects.filter(title_ru__icontains=search).values(
                        "title_ru", "categoryId", "ancestors_ru", "ancestors"
                    )
                else:
                    categories = Category.objects.filter(title__icontains=search).values(
                        "title", "categoryId", "ancestors", "ancestors_ru"
                    )
                categories_count = categories.count()

                if categories_count > 100:
                    categories = categories[:100]

            return Response(
                status=200,
                data={
                    "products": products,
                    "products_count": products_count,
                    "shops": shops,
                    "shops_count": shops_count,
                    "categories": categories,
                    "categories_count": categories_count,
                },
            )
            # generate queries

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=200, data={"products": [], "shops": [], "categories": []})


# Free tariff
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
                .order_by("-total_revenue")[:5]
                .values("shop__title", "total_revenue")
            )

            return Response(shops, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Free tariff
class AllShopsView(APIView):
    permission_classes = [AllowAny]
    serializer_class = ShopSerializer
    queryset = Shop.objects.all()
    allowed_methods = ["GET"]

    @extend_schema(tags=["Shop"])
    def get(self, request: Request):
        try:
            # authorize_Base_tariff(request)
            shops = Shop.objects.all().values("title", "link", "account_id")
            return Response(shops, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class CurrentShopView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Shop"])
    def get(self, request: Request, link: str):
        try:
            authorize_Base_tariff(request)

            user = request.user
            shops = user.shops.all()
            is_owner = False

            if shops.filter(link=link).exists():
                is_owner = True

            shop = Shop.objects.get(link=link)
            serializer = ShopSerializer(shop)
            data = serializer.data
            data["is_owner"] = is_owner
            return Response(data, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class TreemapShopsView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Shop"])
    def get(self, request: Request):
        try:
            authorize_Base_tariff(request)
            shops = (
                ShopAnalytics.objects.filter(date_pretty=get_today_pretty_fake())
                .order_by("-total_revenue")
                .values(
                    "shop__title", "shop__link", "total_orders", "total_products", "total_reviews", "total_revenue"
                )
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


class ShopsExportExcelView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ShopAnalyticsRecentSerializer
    VALID_COLUMNS = [
        "total_products",
        "total_orders",
        "total_reviews",
        "average_purchase_price",
        "rating",
        "monthly_revenue",
        "monthly_orders"
        "quarterly_revenue",
        "quarterly_orders",
        "monthly_transactions"
    ]
    VALID_ORDERS = ["asc", "desc"]
    VALID_SEARCHES = ["title"]

    def get(self, request: Request, *args, **kwargs):
        if request.user.tariff == Tariffs.FREE or request.user.tariff == Tariffs.TRIAL:
            return Response(status=200, data={"data": []})
        queryset = ShopAnalyticsRecent.objects.all().order_by("-monthly_revenue")

        serializer = ShopAnalyticsRecentExcelSerializer(queryset, many=True)

        return Response(serializer.data, status=status.HTTP_200_OK)

# Base tariff
class ShopsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ShopAnalyticsRecentSerializer
    pagination_class = LimitOffsetPagination
    PAGE_SIZE = 100
    VALID_COLUMNS = [
        "total_products",
        "total_orders",
        "total_reviews",
        "average_purchase_price",
        "rating",
        "monthly_revenue",
        "monthly_orders"
        "quarterly_revenue",
        "quarterly_orders",
        "monthly_transactions"
    ]
    VALID_ORDERS = ["asc", "desc"]
    VALID_SEARCHES = ["title"]

    def get_queryset(self):
        date_pretty = get_today_pretty_fake()
        column = self.request.query_params.get("column", "monthly_revenue")
        order = self.request.query_params.get("order", "desc")
        search_columns = self.request.query_params.get("searches", "")
        searches_dict = {}
        filters = self.request.query_params.get("filters", "")

        if search_columns:
            searchs = search_columns.split(",")

            for col in searchs:
                if col not in self.VALID_SEARCHES:
                    raise ValidationError({"error": f"Invalid search column: {col}"})
                searchs[0] = "title"
            filters = filters.split(",")
            for i in range(len(searchs)):
                searches_dict[searchs[i]] = filters[i]

        if column not in self.VALID_COLUMNS:
            raise ValidationError({"error": f"Invalid column: {column}"})
        if order not in self.VALID_ORDERS:
            raise ValidationError({"error": f"Invalid order: {order}"})

        column = f"-{column}" if order == "desc" else column
        queryset = ShopAnalyticsRecent.objects.all().order_by(column)

        # either title or link contains search search_dict['title']
        if searches_dict:
            queryset = queryset.filter(
                Q(title__icontains=searches_dict["title"]) | Q(link__icontains=searches_dict["title"])
            )

        return queryset

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        return response

# Base tariff
class UserShopsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request: Request, *args, **kwargs):
        try:
            authorize_Base_tariff(request)

            user = request.user

            shops = user.shops.all()

            if not shops or len(shops) == 0:
                return Response({"data": []}, status=201)

            # Execute raw SQL
            shop_ids = [shop.seller_id for shop in shops]

            shops = ShopAnalyticsRecent.objects.filter(seller_id__in=shop_ids).order_by("-monthly_revenue")

            serializer = ShopAnalyticsRecentSerializer(shops, many=True)

            return Response({"data": serializer.data}, status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
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
            authorize_Base_tariff(request)
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


# Base tariff
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
            authorize_Base_tariff(request)
            segments = self.shops_segmentation(request)

            return Response(data={"data": segments}, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
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
            if request.user.tariff == Tariffs.FREE or request.user.tariff == Tariffs.TRIAL:
                return Response(status=200, data={"data": []})
            authorize_Base_tariff(request)
            user: User = request.user

            shops = user.shops.all()

            if not shops.filter(seller_id=seller_id).exists() and user.tariff != Tariffs.BUSINESS:
                return Response(status=status.HTTP_403_FORBIDDEN)

            days = get_days_based_on_tariff(user)
            # get start_date 00:00 in Asia/Tashkent timezone which is range days ago
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=days + 1), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            date_pretty = get_today_pretty_fake()

            end_date = timezone.make_aware(
                datetime.strptime(date_pretty, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=20, minute=59, second=59, microsecond=999999)

            if seller_id is None:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT sa.id, sa.total_products, sa.total_orders, sa.total_reviews, sa.total_revenue,
                        sa.average_purchase_price, sa.daily_revenue, sa.daily_orders, sa.rating,
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


# Base tariff
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

            if not shop_categories_ids_str:
                return []

            query = f"""
                WITH CurrentShopRevenue AS (
                    SELECT total_revenue as current_shop_revenue
                    FROM shop_shopanalytics
                    WHERE shop_id = {shop.seller_id}
                    AND date_pretty = '{date_pretty}'
                )

                SELECT
                    sa.shop_id, s.title, s.link, COUNT(DISTINCT sac.category_id) as common_categories_count,
                    sa.total_revenue,
                    STRING_AGG(DISTINCT c.title, ', ') as common_categories_titles,
                    STRING_AGG(DISTINCT c.title_ru, ', ') as common_categories_titles_ru,
                    STRING_AGG(DISTINCT c."categoryId"::text, ', ') as common_categories_ids,
                    ABS(sa.total_revenue - (SELECT current_shop_revenue FROM CurrentShopRevenue)) as revenue_difference
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
                    sa.shop_id, s.title, s.link, sa.total_revenue
                ORDER BY
                    sa.shop_id != {shop.seller_id},  -- prioritize the current shop
                    common_categories_count DESC,
                    revenue_difference  -- order by how close they are to the current shop in terms of revenue
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
            authorize_Base_tariff(request)
            user: User = request.user
            shops = user.shops.all()

            if not shops.filter(seller_id=seller_id).exists() and user.tariff != Tariffs.BUSINESS:
                return Response(status=status.HTTP_403_FORBIDDEN)

            if seller_id is None:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            shop = get_object_or_404(Shop, seller_id=seller_id)
            days = get_days_based_on_tariff(user)
            print(days, request.user)
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=int(days) + 1), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)

            end_date = timezone.make_aware(
                datetime.strptime(get_today_pretty_fake(), "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=20, minute=59, second=59, microsecond=999999)

            competitor_shops_data = self.get_competitor_shops(shop)

            competitors_data = []
            for (
                shop_id,
                title,
                link,
                common_categories_count,
                total_revenue,
                common_categories_titles,
                common_categories_titles_ru,
                common_categories_ids,
                revenue_difference,
            ) in competitor_shops_data:
                competitors_data.append(
                    {
                        "title": title,
                        "link": link,
                        "shop_id": shop_id,
                        "common_categories_count": common_categories_count,
                        "common_categories_titles": common_categories_titles.split(","),
                        "common_categories_ids": common_categories_ids.split(","),  # convert to list,
                        "common_categories_titles_ru": common_categories_titles_ru.split(","),
                    }
                )

            shop_analytics = (
                ShopAnalytics.objects.filter(shop=shop, created_at__range=[start_date, end_date])
                .annotate(category_count=Count("categories"))
                .values(
                    "id",
                    "total_products",
                    "total_orders",
                    "total_reviews",
                    "average_purchase_price",
                    "average_order_price",
                    "rating",
                    "date_pretty",
                    "category_count",
                    "total_revenue",
                )
            )
            shop_analytics_data = list(shop_analytics)

            return Response(data={"data": competitors_data, "shop": shop_analytics_data}, status=status.HTTP_200_OK)
        except Shop.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Shop not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


# Base tariff
class ShopDailySalesView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request: Request, seller_id: int):
        """
        Get Productanalytics of a shop at a specific date and next day
        """
        try:
            authorize_Base_tariff(request)
            user: User = request.user

            shops = user.shops.all()

            if not shops.filter(seller_id=seller_id).exists() and user.tariff != Tariffs.BUSINESS:
                return Response(status=status.HTTP_403_FORBIDDEN)

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

            user: User = request.user

            # check if start date is before 30 days
            if start_date < timezone.make_aware(
                datetime.now() - timedelta(days=30), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0):
                if user.tariff == Tariffs.SELLER or user.tariff == Tariffs.BUSINESS or user.tariff == Tariffs.BASE:
                    pass
                else:
                    start_date = timezone.make_aware(
                        datetime.now() - timedelta(days=30), timezone=pytz.timezone("Asia/Tashkent")
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
                    "product__title_ru",
                    "product__category__title",
                    "product__category__title_ru",
                    "product__product_id",
                    "product__category__categoryId",
                    "product__photos",
                    "date_pretty",
                    "real_orders_amount",
                    "daily_revenue",
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
                "product__title_ru",
                "product__category__title",
                "product__category__title_ru",
                "product__product_id",
                "product__category__categoryId",
                "date_pretty",
            )

            target_analytics = list(analytics_date)

            before_analytics_dict = {i["product__product_id"]: i for i in day_before_analytics}

            for item in target_analytics:
                before_item = before_analytics_dict.get(item["product__product_id"], None)
                item["product__title"] += f'(({item["product__product_id"]}))'
                item["product__category__title"] += f'(({item["product__category__categoryId"]}))'
                item["product__title_ru"] = (
                    item["product__title_ru"] if item["product__title_ru"] else item["product__title"]
                ) + f'(({item["product__product_id"]}))'
                item["product__category__title_ru"] = (
                    item["product__category__title_ru"]
                    if item["product__category__title_ru"]
                    else item["product__category__title"]
                ) + f'(({item["product__category__categoryId"]}))'

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

            return Response(
                final_res,
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


# Base tariff
class ShopProductsView(ListAPIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ProductAnalyticsViewSerializer
    pagination_class = LimitOffsetPagination

    VALID_FILTER_FIELDS = ["category_title", "product_title"]

    def get_queryset(self):
        """
        This view should return a list of all the products for
        the category as determined by the category portion of the URL.
        """
        seller_id = self.kwargs["seller_id"]

        shop = get_object_or_404(Shop, seller_id=seller_id)
        link = shop.link

        ordering = self.request.query_params.get("order", "desc")
        column = self.request.query_params.get("column", "orders_money")
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

        return ProductAnalyticsView.objects.filter(shop_link=link).filter(filter_query).order_by(order_by_column)

    def list(self, request, *args, **kwargs):
        authorize_Base_tariff(request)

        start_time = time.time()
        print("Shop PRODUCTS")
        response = super().list(request, *args, **kwargs)
        print(f"Shop PRODUCTS: {time.time() - start_time} seconds")
        return response


# Base tariff
class ShopTopProductsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ProductAnalyticsViewSerializer

    def get(self, request: Request, seller_id: int):
        try:
            """
            This view should return a list of all the products for
            the category as determined by the category portion of the URL.
            """
            authorize_Base_tariff(request)

            # user: User = request.user
            # shops = user.shops.all()

            # if not shops.filter(seller_id=seller_id).exists() and user.tariff != Tariffs.BUSINESS:
            #     return Response(status=status.HTTP_403_FORBIDDEN, data={"message": "You don't have access to this shop"})

            seller_id = self.kwargs["seller_id"]
            shop = Shop.objects.get(seller_id=seller_id)

            latest_analytics = ShopAnalyticsRecent.objects.get(seller_id=seller_id)
            products = ProductAnalyticsView.objects.filter(shop_link=shop.link)

            n = 10 if products.count() < 20 else 20

            orders_products = products.order_by("-monthly_orders")[:n]
            reviews_products = products.order_by("-reviews_amount")[:n]
            revenue_products = products.order_by("-monthly_revenue")[:n]

            return Response(
                data={
                    "orders_products": ProductAnalyticsViewSerializer(orders_products, many=True).data,
                    "reviews_products": ProductAnalyticsViewSerializer(reviews_products, many=True).data,
                    "revenue_products": ProductAnalyticsViewSerializer(revenue_products, many=True).data,
                    "total_orders": latest_analytics.monthly_orders,
                    "total_revenue": latest_analytics.monthly_revenue,
                },
                status=status.HTTP_200_OK,
            )
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=201, data={"orders_products": [], "reviews_products": [], "revenue_products": [], "total_orders": 0, "total_reviews": 0, "total_revenue": 0})


# Base tariff
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
            authorize_Base_tariff(request)

            # user: User = request.user
            # shops = user.shops.all()

            # if not shops.filter(seller_id=seller_id).exists() and user.tariff != Tariffs.BUSINESS:
            #     return Response(
            #         status=status.HTTP_403_FORBIDDEN, data={"message": "You don't have access to this shop"}
            #     )
            start = time.time()
            query = f"""
            SELECT p.title as product_title, p.title_ru, pa.*, p.photos, c.title AS category_title, c.title_ru AS category_title_ru, c."categoryId" as category_id,  AVG(ska.purchase_price) AS avg_purchase_price, AVG(ska.full_price) AS avg_full_price
            FROM product_product p
            INNER JOIN category_category c ON p.category_id = c."categoryId"
            INNER JOIN (
                SELECT pa_inner.*
                FROM product_productanalytics pa_inner
                WHERE pa_inner.created_at IN (
                    SELECT MAX(pa2.created_at)
                    FROM product_productanalytics pa2
                    WHERE pa2.product_id = pa_inner.product_id
                ) AND pa_inner.created_at <= NOW() - INTERVAL '1 days'
            ) pa ON p.product_id = pa.product_id
            LEFT JOIN sku_sku s ON p.product_id = s.product_id
            LEFT JOIN sku_skuanalytics ska ON s.sku = ska.sku_id AND pa.date_pretty = ska.date_pretty
            WHERE p.shop_id = {seller_id}
            GROUP BY p.title, p.title_ru, pa.id, pa.score, c.title, c."categoryId", p.photos, pa.created_at, pa.date_pretty, pa.product_id, pa.reviews_amount, pa.orders_amount, pa.rating, pa.available_amount, pa.orders_money, pa.position, pa.position_in_category, pa.position_in_shop, pa.average_purchase_price, pa.real_orders_amount, pa.daily_revenue, pa.positions
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
                row["title_ru"] = (
                    row["title_ru"] if row["title_ru"] else row["product_title"]
                ) + f'(({row["product_id"]}))'
                row["title"] = row["product_title"] + f'(({row["product_id"]}))'
                row["category_title"] = row["category_title"] + f'(({row["category_id"]}))'
                row["category_title_ru"] = (
                    row["category_title_ru"] if row["category_title_ru"] else row["category_title"]
                ) + f'(({row["category_id"]}))'

            print(f"STOPPED PRODUCTS: {time.time() - start} seconds")
            return Response(data=result, status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


# Base tariff
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
            authorize_Base_tariff(request)
            user: User = request.user
            shops = user.shops.all()

            if not shops.filter(seller_id=seller_id).exists() and user.tariff != Tariffs.BUSINESS:
                return Response(
                    status=status.HTTP_403_FORBIDDEN, data={"message": "You don't have access to this shop"}
                )
            start = time.time()
            query = f"""
            SELECT c."categoryId", c.title, c.title_ru, COUNT(p.product_id) AS products_amount, SUM(pa.orders_amount) AS orders_amount, SUM(pa.reviews_amount) AS reviews_amount
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
            GROUP BY c."categoryId", c.title, c.title_ru
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


# Base tariff
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
            authorize_Base_tariff(request)
            user: User = request.user
            shops = user.shops.all()

            if not shops.filter(seller_id=seller_id).exists() and user.tariff != Tariffs.BUSINESS:
                return Response(
                    status=status.HTTP_403_FORBIDDEN, data={"message": "You don't have access to this shop"}
                )
            print("SHOP CATEGORY ANALYTICS")

            days = get_days_based_on_tariff(user)
            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=days), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=20, minute=59, second=59, microsecond=999999)

            current_date = timezone.make_aware(
                datetime.strptime(get_today_pretty_fake(), "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=20, minute=59, second=59, microsecond=999999)

            if category_id == 1:
                # return shop analytics for dates between start_date and current_date
                sa = (
                    ShopAnalytics.objects.filter(shop_id=seller_id, created_at__range=[start_date, current_date])
                    .order_by("created_at")
                    .values(
                        "date_pretty",
                        "total_orders",
                        "total_reviews",
                        "total_products",
                        "total_revenue",
                        "average_purchase_price",
                    )
                )

                return Response(data=sa, status=status.HTTP_200_OK)

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
                            pa.orders_money,
                            pa.average_purchase_price,
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
                            SUM(la.orders_money) AS total_revenue,
                            AVG(la.average_purchase_price) AS average_purchase_price,
                            COUNT(*) FILTER (WHERE la.row_number = 1) AS total_products
                        FROM latest_analytics AS la
                        WHERE la.row_number = 1
                        GROUP BY la.date
                    )
                    SELECT
                        aa.date,
                        aa.total_orders,
                        aa.total_reviews,
                        aa.total_products,
                        aa.total_revenue,
                        aa.average_purchase_price
                    FROM aggregated_analytics AS aa
                    ORDER BY aa.date
                """,
                    [start_date, current_date, seller_id, category_id],
                )

                res = [
                    {
                        "category_id": category_id,
                        "date_pretty": date.strftime("%Y-%m-%d"),
                        "total_orders": total_orders,
                        "total_products": total_products,
                        "total_revenue": total_revenue,
                        "total_reviews": total_reviews,
                        "average_purchase_price": average_purchase_price,
                    }
                    for date, total_orders, total_reviews, total_products, total_revenue, average_purchase_price in cursor.fetchall()
                ]

            print(f"SHOP CATEGORY ANALYTICS: {time.time() - start} seconds")
            return Response(data=res, status=status.HTTP_200_OK)

        except Shop.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"detail": "Shop not found."})

        except Exception as e:
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"detail": str(e)})


# Base tariff
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
            authorize_Base_tariff(request)
            user: User = request.user
            shops = user.shops.all()

            if not shops.filter(seller_id=seller_id).exists() and user.tariff != Tariffs.BUSINESS:
                return Response(
                    status=status.HTTP_403_FORBIDDEN, data={"message": "You don't have access to this shop"}
                )

            shop = Shop.objects.get(pk=seller_id)
            category = Category.objects.get(pk=category_id)

            categories = category.get_category_descendants(include_self=True)
            latest_product_analytics_orders_amount = Subquery(
                ProductAnalytics.objects.filter(product__product_id=OuterRef("product_id"))
                .order_by("-created_at")
                .values("orders_amount")[:1],
                output_field=IntegerField(),
            )

            latest_product_analytics_reviews_amount = Subquery(
                ProductAnalytics.objects.filter(product__product_id=OuterRef("product_id"))
                .order_by("-created_at")
                .values("reviews_amount")[:1],
                output_field=IntegerField(),
            )

            latest_product_analytics_available_amount = Subquery(
                ProductAnalytics.objects.filter(product__product_id=OuterRef("product_id"))
                .order_by("-created_at")
                .values("available_amount")[:1],
                output_field=IntegerField(),
            )

            latest_product_analytics_money = Subquery(
                ProductAnalytics.objects.filter(product__product_id=OuterRef("product_id"))
                .order_by("-created_at")
                .values("orders_money")[:1],
                output_field=CharField(),
            )

            latest_product_analytics_date = Subquery(
                ProductAnalytics.objects.filter(product__product_id=OuterRef("product_id"))
                .order_by("-created_at")
                .values("date_pretty")[:1],
                output_field=CharField(),
            )

            products = (
                Product.objects.filter(shop=shop, category__in=categories)
                .values(
                    "product_id",
                    "title",
                    "title_ru",
                    "photos",
                )
                .annotate(
                    latest_product_analytics_date=latest_product_analytics_date,
                    latest_product_analytics_orders_amount=latest_product_analytics_orders_amount,
                    latest_product_analytics_reviews_amount=latest_product_analytics_reviews_amount,
                    latest_product_analytics_available_amount=latest_product_analytics_available_amount,
                    latest_product_analytics_money=latest_product_analytics_money,
                )
            )

            for product in products:
                product["title"] = product["title"] + f'(({product["product_id"]}))'
                product["title_ru"] = (
                    product["title_ru"] if product["title_ru"] else product["title"]
                ) + f'(({product["product_id"]}))'

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


# Free tariff
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
            user: User = request.user
            days = get_days_based_on_tariff(user)
            # start_date = timezone.make_aware(
            #     datetime.now() - timedelta(days=days), timezone=pytz.timezone("Asia/Tashkent")
            # ).replace(hour=0, minute=0, second=0, microsecond=0)

            data = ShopAnalyticsTable.objects.all().values("date_pretty", "total_orders").order_by("date_pretty")

            # exclude "2023-06-22" and "2023-07-23"
            data = [d for d in data if d["date_pretty"] not in ["2023-06-22", "2023-07-23"]][days * -1 :]

            return Response(list(data), status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Free tariff
class UzumTotalReviews(APIView):
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
            user: User = request.user
            days = get_days_based_on_tariff(user)
            # start_date = timezone.make_aware(
            #     datetime.now() - timedelta(days=days), timezone=pytz.timezone("Asia/Tashkent")
            # ).replace(hour=0, minute=0, second=0, microsecond=0)

            data = ShopAnalyticsTable.objects.all().values("date_pretty", "total_reviews").order_by("date_pretty")

            # exclude "2023-06-22" and "2023-07-23"
            data = [d for d in data if d["date_pretty"] not in ["2023-06-22", "2023-07-23"]][days * -1 :]

            return Response(list(data), status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Free tariff
class UzumTotalRevenue(APIView):
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
            user: User = request.user
            days = get_days_based_on_tariff(user)
            # start_date = timezone.make_aware(
            #     datetime.now() - timedelta(days=days), timezone=pytz.timezone("Asia/Tashkent")
            # ).replace(hour=0, minute=0, second=0, microsecond=0)

            data = ShopAnalyticsTable.objects.all().values("date_pretty", "total_revenue").order_by("date_pretty")

            # exclude "2023-06-22" and "2023-07-23"
            data = [d for d in data if d["date_pretty"] not in ["2023-06-22", "2023-07-23"]][days * -1 :]

            return Response(list(data), status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Free tariff
class UzumTotalProducts(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request):
        try:
            user: User = request.user
            days = get_days_based_on_tariff(user)
            now_tz = datetime.now().astimezone(pytz.timezone("Asia/Tashkent"))
            start_date = (now_tz - timedelta(days=days)).replace(hour=0, minute=0, second=0, microsecond=0)
            date_pretty = get_today_pretty_fake()

            end_date = timezone.make_aware(
                datetime.strptime(date_pretty, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=20, minute=59, second=59, microsecond=999999)

            product_analytics = ProductAnalytics.objects.only("created_at", "product__product_id").filter(
                created_at__range=[start_date, end_date]
            )
            daily_totals = (
                product_analytics.values("date_pretty")
                .annotate(total_products=Count("product__product_id"))
                .values("date_pretty", "total_products")
                .order_by("date_pretty")
            )
            return Response(daily_totals, status=status.HTTP_200_OK)
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Free tariff
class UzumTotalShops(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request: Request):
        try:
            user: User = request.user
            days = get_days_based_on_tariff(user)

            start_date = timezone.make_aware(
                datetime.now() - timedelta(days=days), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=0, minute=0, second=0, microsecond=0)
            date_pretty = get_today_pretty_fake()

            end_date = timezone.make_aware(
                datetime.strptime(date_pretty, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            ).replace(hour=20, minute=59, second=59, microsecond=999999)

            product_analytics = ShopAnalytics.objects.filter(created_at__range=[start_date, end_date])
            daily_totals = (
                product_analytics.values("date_pretty")
                .annotate(total_shops=Count("shop__seller_id"))
                .values("date_pretty", "total_shops")
                .order_by("date_pretty")
            )

            daily_accounts_totals = (
                product_analytics.values("date_pretty")
                .annotate(total_accounts=Count("shop__account_id", distinct=True))
                .values("date_pretty", "total_accounts")
                .order_by("date_pretty")
            )

            return Response(
                {"shops": list(daily_totals), "accounts": list(daily_accounts_totals)}, status=status.HTTP_200_OK
            )
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Free tariff
class ShopsWithMostRevenueYesterdayView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request: Request):
        """
        Return top 5 shops which had themost orders yesterday
        """
        try:
            start = time.time()
            date_pretty = get_today_pretty_fake()
            yesterday_pretty = get_day_before_pretty(date_pretty)

            shop_with_no_sales = ShopAnalytics.objects.filter(date_pretty=date_pretty, total_orders=0).count()
            shops_with_no_reviews = ShopAnalytics.objects.filter(date_pretty=date_pretty, total_reviews=0).count()

            def dictfetchall(cursor):
                "Returns all rows from a cursor as a dict"
                desc = cursor.description
                return [dict(zip([col[0] for col in desc], row)) for row in cursor.fetchall()]

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        COUNT(today.shop_id) as shops_with_sales_yesterday
                    FROM
                        (
                        SELECT
                            shop_id,
                            total_orders
                        FROM
                            shop_shopanalytics
                        WHERE
                            date_pretty = %s
                        ) as today
                    INNER JOIN
                        (
                        SELECT
                            shop_id,
                            total_orders
                        FROM
                            shop_shopanalytics
                        WHERE
                            date_pretty = %s
                        ) as yesterday
                    ON
                        today.shop_id = yesterday.shop_id
                    WHERE
                        today.total_orders - COALESCE(yesterday.total_orders, 0) > 0
                    """,
                    [date_pretty, yesterday_pretty],
                )

                res = dictfetchall(cursor)
                shops_with_sales_yesterday = res[0]["shops_with_sales_yesterday"]

                cursor.execute(
                    """
                    SELECT
                        COUNT(today.shop_id) as shops_with_reviews_yesterday
                    FROM
                        (
                        SELECT
                            shop_id,
                            total_reviews
                        FROM
                            shop_shopanalytics
                        WHERE
                            date_pretty = %s
                        ) as today
                    INNER JOIN
                        (
                        SELECT
                            shop_id,
                            total_reviews
                        FROM
                            shop_shopanalytics
                        WHERE
                            date_pretty = %s
                        ) as yesterday
                    ON
                        today.shop_id = yesterday.shop_id
                    WHERE
                        today.total_reviews - COALESCE(yesterday.total_reviews, 0) > 0
                    """,
                    [date_pretty, yesterday_pretty],
                )

                res = dictfetchall(cursor)
                shops_with_reviews_yesterday = res[0]["shops_with_reviews_yesterday"]

                cursor.execute(
                    """
                    SELECT
                        today.shop_id,
                        today.total_revenue - COALESCE(yesterday.total_revenue, 10000000000) as diff_revenue
                    FROM
                        (
                        SELECT
                            shop_id,
                            total_revenue
                        FROM
                            shop_shopanalytics
                        WHERE
                            date_pretty = %s
                        ) as today
                    INNER JOIN
                        (
                        SELECT
                            shop_id,
                            total_revenue
                        FROM
                            shop_shopanalytics
                        WHERE
                            date_pretty = %s
                        ) as yesterday
                    ON
                        today.shop_id = yesterday.shop_id
                    INNER JOIN
                        shop_shop as shop
                    ON
                        today.shop_id = shop.seller_id
                    ORDER BY
                        diff_revenue DESC
                    LIMIT 5
                """,
                    [date_pretty, yesterday_pretty],
                )

                res = dictfetchall(cursor)
                shop_ids = [row["shop_id"] for row in res]
                shop_ids_tuple = tuple(shop_ids)
                start_date = timezone.make_aware(
                    datetime.now() - timedelta(days=7), timezone=pytz.timezone("Asia/Tashkent")
                ).replace(hour=0, minute=0, second=0, microsecond=0)

                end_date = timezone.make_aware(
                    datetime.strptime(date_pretty, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
                ).replace(hour=20, minute=59, second=59, microsecond=999999)

                cursor.execute(
                    """
                    SELECT
                        analytics.shop_id,
                        shop.title AS shop_title,
                        analytics.total_orders,
                        analytics.total_reviews,
                        analytics.total_revenue,
                        analytics.total_products,
                        analytics.date_pretty,
                        analytics.average_purchase_price
                    FROM
                        shop_shopanalytics AS analytics
                    INNER JOIN
                        shop_shop AS shop
                    ON
                        analytics.shop_id = shop.seller_id
                    WHERE
                        analytics.shop_id IN %s AND analytics.created_at >= %s AND analytics.created_at <= %s
                    ORDER BY
                        analytics.shop_id, analytics.date_pretty DESC
                    """,
                    [shop_ids_tuple, start_date, end_date],
                )
                rows = dictfetchall(cursor)

                # Group results by shop_id
                grouped_data = []
                for row in rows:
                    shop_id = row["shop_id"]
                    shop_title = row["shop_title"] + f"(({shop_id}))"

                    # Check if the shop is already in the grouped_data list
                    shop_entry = next((item for item in grouped_data if item["id"] == shop_id), None)
                    # print(shop_entry)

                    if not shop_entry:
                        # If not, create a new shop entry
                        shop_entry = {
                            "id": shop_id,
                            "title": shop_title,
                            "total_orders": row["total_orders"],
                            "total_reviews": row["total_reviews"],
                            "total_revenue": [],
                            "total_products": row["total_products"],
                            "date_pretty": row["date_pretty"],
                            "average_purchase_price": row["average_purchase_price"],
                        }
                        grouped_data.append(shop_entry)

                    # Append data to the shop entry
                    # shop_entry["total_orders"].append(row["total_orders"])
                    # shop_entry["total_reviews"].append(row["total_reviews"])
                    shop_entry["total_revenue"].append(row["total_revenue"])
                    # shop_entry["total_products"].append(row["total_products"])
                    # shop_entry["average_purchase_price"].append(row["average_purchase_price"])
                    # shop_entry["date_pretty"].append(row["date_pretty"])

            print("Time taken by yesterday top shops ", time.time() - start)
            return Response(
                {
                    "shops_with_sales_yesterday": shops_with_sales_yesterday,
                    "shop_with_no_sales": shop_with_no_sales,
                    "shops": grouped_data,
                    "shops_with_reviews_yesterday": shops_with_reviews_yesterday,
                    "shops_with_no_reviews": shops_with_no_reviews,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# Base tariff
class YesterdayTopsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    def get(self, request: Request):
        """
        Return top 20 shops which had themost orders yesterday
        """
        try:
            authorize_Base_tariff(request)
            date_pretty = get_today_pretty_fake()
            yesterday_pretty = get_day_before_pretty(date_pretty)

            def dictfetchall(cursor):
                "Returns all rows from a cursor as a dict"
                desc = cursor.description
                return [dict(zip([col[0] for col in desc], row)) for row in cursor.fetchall()]

            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                        today.shop_id,
                        shop.title,
                        today.total_orders - COALESCE(yesterday.total_orders, 10000000) as diff_orders,
                        today.total_reviews - COALESCE(yesterday.total_reviews, 10000000) as diff_reviews,
                        today.total_revenue - COALESCE(yesterday.total_revenue, 10000000000) as diff_revenue
                    FROM
                        (
                        SELECT
                            shop_id,
                            total_orders,
                            total_reviews,
                            total_revenue
                        FROM
                            shop_shopanalytics
                        WHERE
                            date_pretty = %s
                        ) as today
                    LEFT JOIN
                        (
                        SELECT
                            shop_id,
                            total_orders,
                            total_reviews,
                            total_revenue
                        FROM
                            shop_shopanalytics
                        WHERE
                            date_pretty = %s
                        ) as yesterday
                    ON
                        today.shop_id = yesterday.shop_id
                    INNER JOIN
                        shop_shop as shop
                    ON
                        today.shop_id = shop.seller_id
                    ORDER BY
                        diff_revenue DESC,
                        diff_orders DESC,
                        diff_reviews DESC
                    LIMIT 20
                """,
                    [date_pretty, yesterday_pretty],
                )
                res = dictfetchall(cursor)
                # column_names = [column[0] for column in cursor.description]
                # result = [dict(zip(column_names, row)) for row in rows]

            return Response(res, status=status.HTTP_200_OK)

        except Exception as e:
            print(e)
            return Response({"error": "Something went wrong"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
