import math
import traceback
from datetime import datetime, timedelta

import pytz
from django.db.models import Avg, Count, F, FloatField, Max, Min, OuterRef, Q, Subquery, Sum
from django.db.models.functions import Coalesce, TruncDate
from django.utils import timezone
from rest_framework import status
from rest_framework_simplejwt.authentication import JWTAuthentication
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from drf_spectacular.utils import extend_schema

from uzum.category.models import Category
from uzum.product.models import Product, ProductAnalytics
from uzum.product.serializers import ProductSerializer


from .models import Shop, ShopAnalytics
from .serializers import ExtendedShopSerializer, ShopAnalyticsSerializer, ShopCompetitorsSerializer, ShopSerializer


class ShopsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ShopSerializer
    queryset = Shop.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @extend_schema(tags=["Shop"])
    def get(self, request: Request):
        try:
            shops = Shop.objects.all()
            # paginate the queryset
            paginator = PageNumberPagination()
            shops_serizalized = ShopSerializer(shops, many=True)

            page = paginator.paginate_queryset(shops_serizalized.data, request)

            if page is not None:
                return paginator.get_paginated_response(page)

            print("Page is None")
            return Response(
                status=status.HTTP_200_OK,
                data={
                    "data": shops_serizalized.data,
                    "total": len(shops_serizalized.data),
                },
            )

            # return Response(data={"data": ShopSerializer(shops, many=True).data}, status=status.HTTP_200_OK)
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
                "start_date", (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
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
            start_date_str = request.query_params.get(
                "start_date", (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            )

            start_date = timezone.make_aware(
                datetime.strptime(start_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            )

            if seller_id is None:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            shop = Shop.objects.get(pk=seller_id)

            analytics = ShopAnalytics.objects.filter(shop=shop, created_at__gte=start_date).order_by("-created_at")

            return Response(
                data={"data": ShopAnalyticsSerializer(analytics, many=True).data}, status=status.HTTP_200_OK
            )

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

    @extend_schema(tags=["Shop"])
    def get(self, request: Request, seller_id: int):
        try:
            if seller_id is None:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            shop = Shop.objects.get(pk=seller_id)
            latest_analytics = ShopAnalytics.objects.filter(shop=shop).order_by("-created_at")[0]
            date_pretty = latest_analytics.date_pretty
            categories = latest_analytics.categories.all()

            if len(categories) == 0:
                return Response(status=status.HTTP_200_OK, data={"shops": [], "total": 0})

            # get all competitor shops in each category
            competitors: list[dict] = []

            for category in categories:
                analytics = (
                    ShopAnalytics.objects.filter(date_pretty=date_pretty, categories__in=[category])
                    .exclude(shop=shop)
                    .annotate(
                        title=F("shop__title"),
                        seller_id=F("shop__seller_id"),
                        description=F("shop__description"),
                    )
                )

                competitors.append({category.title: ShopCompetitorsSerializer(analytics, many=True).data})

            return Response(data={"data": competitors}, status=status.HTTP_200_OK)
        except Shop.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Shop not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


class ShopProductsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ProductSerializer
    queryset = Shop.objects.all()
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @extend_schema(tags=["Shop"])
    def get(self, request: Request, seller_id: int):
        try:
            if seller_id is None:
                return Response(status=status.HTTP_400_BAD_REQUEST)

            shop = Shop.objects.get(pk=seller_id)
            products = Product.objects.filter(shop=shop)

            paginator = PageNumberPagination()

            page = paginator.paginate_queryset(products, request)

            if page is not None:
                serializer = ProductSerializer(page, many=True)
                return paginator.get_paginated_response(serializer.data)

            return Response(
                data={"data": ProductSerializer(products, many=True).data, "total": len(products)},
                status=status.HTTP_200_OK,
            )
        except Shop.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"message": "Shop not found"})
        except Exception as e:
            print(e)
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"message": "Internal server error"})


class ShopCategoryAnalyticsView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    serializer_class = ShopAnalyticsSerializer
    allowed_methods = ["GET"]
    pagination_class = PageNumberPagination

    @extend_schema(tags=["Shop"])
    def get(self, request: Request, seller_id: int):
        if seller_id is None:
            return Response(status=status.HTTP_400_BAD_REQUEST)

        try:
            start_date_str = request.query_params.get(
                "start_date", (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            )

            start_date = timezone.make_aware(
                datetime.strptime(start_date_str, "%Y-%m-%d"), timezone=pytz.timezone("Asia/Tashkent")
            )

            shop = Shop.objects.get(pk=seller_id)

            # Get all relevant ShopAnalytics at once
            shop_analytics = (
                ShopAnalytics.objects.filter(shop=shop, created_at__gte=start_date)
                .annotate(date=TruncDate("created_at"))
                .values("date", "total_orders", "total_reviews", "rating", "total_products")
            )

            # Get all relevant ProductAnalytics at once
            product_analytics = (
                ProductAnalytics.objects.filter(product__shop=shop, created_at__gte=start_date)
                .annotate(date=TruncDate("created_at"))
                .values("product__category__title", "date")
                .annotate(
                    total_orders=Sum("orders_amount"),
                    total_reviews=Sum("reviews_amount"),
                    rating=Coalesce(Avg("rating", filter=Q(rating__gt=0)), 0, output_field=FloatField()),
                    total_products=Count("product_id"),
                    total_available_amount=Sum("available_amount"),
                )
            )

            # Format the results
            res = {}
            for analytics in shop_analytics:
                date = analytics.pop("date").strftime("%Y-%m-%d")
                if date not in res:
                    res[date] = analytics
                    res[date]["categories"] = {}

            for analytics in product_analytics:
                date = analytics.pop("date").strftime("%Y-%m-%d")
                category = analytics.pop("product__category__title")
                if date in res:
                    res[date]["categories"][category] = analytics

            return Response(data={"data": res}, status=status.HTTP_200_OK)

        except Shop.DoesNotExist:
            return Response(status=status.HTTP_404_NOT_FOUND, data={"detail": "Shop not found."})

        except Exception as e:
            traceback.print_exc()
            return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR, data={"detail": str(e)})


class ShopProductsByCategoryView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
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

            products = Product.objects.filter(shop=shop, category__in=categories).order_by("-created_at")

            paginator = PageNumberPagination()

            page = paginator.paginate_queryset(products, request)

            if page is not None:
                serializer = ProductSerializer(page, many=True)
                return paginator.get_paginated_response(serializer.data)

            return Response(
                data={"data": ProductSerializer(products, many=True).data, "total": len(products)},
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
