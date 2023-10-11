import datetime
import time
import traceback
from datetime import timedelta

import pytz
from django.db.models import F, Max, Min, OuterRef, Subquery
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from uzum.banner.models import Banner
from uzum.banner.serializers import BannerSerializer
# from uzum.category.utils import seconds_until_next
from uzum.product.models import Product, ProductAnalytics
from uzum.product.serializers import ProductAnalyticsSerializer
from uzum.utils.general import (authorize_Seller_tariff, get_day_before_pretty,
                                get_today_pretty_fake)


class BannersView(APIView):
    """
    Get all banners with product analytics
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    serializer_class = BannerSerializer

    @extend_schema(tags=["Banner"])
    def get(self, request):
        try:
            start = time.time()
            authorize_Seller_tariff(request)
            banners = (
                Banner.objects.exclude(product=None)  # Exclude banners without a product
                .values("product")  # Group by product
                .annotate(
                    earliest_date=Min("created_at"),
                    latest_date=Max("created_at"),
                )  # Get the earliest and latest date for each product
                .order_by("product")
            )

            # create mapping from product id to entry in banners
            d = {banner["product"]: banner for banner in list(banners)}

            productIds = [banner["product"] for banner in list(banners)]

            date_pretty = get_today_pretty_fake()
            date = (
                datetime.datetime.strptime(date_pretty, "%Y-%m-%d")
                .astimezone(pytz.timezone("Asia/Tashkent"))
                .replace(hour=23, minute=59, second=0, microsecond=0)
            )

            latest_analytics_subquery = (
                ProductAnalytics.objects.filter(
                    product__product_id=OuterRef("product__product_id"), created_at__lte=date
                )
                .order_by("-created_at")
                .values("created_at")[:1]
            )

            analytics = (
                ProductAnalytics.objects.select_related("product")
                .filter(product__product_id__in=productIds, created_at__lte=date)
                .annotate(latest_created_at=Subquery(latest_analytics_subquery))
                .filter(created_at=F("latest_created_at"))
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

                product["product__title_ru"] = (
                    product["product__title_ru"] if product["product__title_ru"] else product["product__title"]
                ) + f"(({product['product__product_id']}))"

                product["product__category__title_ru"] += f"(({product['product__category__categoryId']}))"
                product["first_date"] = (
                    d[product["product__product_id"]]["earliest_date"]
                    .astimezone(pytz.timezone("Asia/Tashkent"))
                    .strftime("%Y-%m-%d")
                )
                product["last_date"] = (
                    d[product["product__product_id"]]["latest_date"]
                    .astimezone(pytz.timezone("Asia/Tashkent"))
                    .strftime("%Y-%m-%d")
                )

            print(f"Time taken: {time.time() - start}")
            return Response(analytics, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc(e)
            print(f"Error in BannersView: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class BannerImpactView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]

    @extend_schema(tags=["Banner"])
    def get(self, request, product_id: str):
        try:
            authorize_Seller_tariff(request)

            product = Product.objects.get(product_id=product_id)

            date_pretty = get_today_pretty_fake()
            date = (
                datetime.datetime.strptime(date_pretty, "%Y-%m-%d")
                .astimezone(pytz.timezone("Asia/Tashkent"))
                .replace(hour=23, minute=59, second=0, microsecond=0)
            )

            if not product:
                return Response({"error": "No analytics found for this banner"}, status=status.HTTP_404_NOT_FOUND)

            banner_dates = Banner.objects.filter(product=product).aggregate(
                earliest_date=Min("created_at"), latest_date=Max("created_at")
            )

            earliest_date = banner_dates["earliest_date"] - timedelta(days=20)
            latest_date = banner_dates["latest_date"] + timedelta(weeks=10)

            # check if latest date is less than or equal to date
            if latest_date > date:
                latest_date = date

            product_analytics = ProductAnalytics.objects.filter(
                product=product, created_at__range=[earliest_date, latest_date]
            )

            return Response(
                {
                    "data": ProductAnalyticsSerializer(product_analytics, many=True).data,
                    "first_date": banner_dates["earliest_date"].strftime("%Y-%m-%d"),
                    "last_date": banner_dates["latest_date"]
                    .astimezone(pytz.timezone("Asia/Tashkent"))
                    .strftime("%Y-%m-%d"),
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            traceback.print_exc(e)
            print(f"Error in BannerImpactView: {e}")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OngoingBannersView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    serializer_class = BannerSerializer

    @extend_schema(tags=["Banner"])
    def get(self, request):
        try:
            authorize_Seller_tariff(request)
            banners = Banner.objects.all()
            date_pretty = get_today_pretty_fake()
            date_pretty = get_day_before_pretty(date_pretty)

            product_analytics_today = ProductAnalytics.objects.filter(date_pretty=date_pretty)
            banners = Banner.objects.filter(productanalytics__in=product_analytics_today)

            response_data = []

            # Serialize the banners and associate with respective product
            for banner in banners:
                # Fetch the product associated with the banner
                product = banner.productanalytics_set.all()[0].product
                product_data = {
                    "id": product.product_id,
                    "name": product.title,
                }
                # Serialize the banner
                banner_data = BannerSerializer(banner).data
                # Combine banner and product data
                combined_data = {**banner_data, "product": product_data}
                response_data.append(combined_data)

            return Response(response_data, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# class BannerImpactView(APIView):
#     permission_classes = [IsAuthenticated]
#     authentication_classes = [JWTAuthentication]
#     allowed_methods = ["GET"]
#     serializer_class = BannerSerializer

#     @extend_schema(tags=["Banner"])
#     def get(self, request, banner_id: str):
#         try:
#             banner = Banner.objects.get(id=banner_id)

#             analytics = banner.productanalytics_set.all()

#             if len(analytics) == 0:
#                 return Response({"error": "No analytics found for this banner"}, status=status.HTTP_404_NOT_FOUND)

#             product = analytics[0].product

#             # get first day banner was used with productanalytics
#             first_date: datetime = analytics.order_by("created_at")[0].created_at

#             # now get week before in Asia/Tashkent timezone
#             week_before = (first_date - datetime.timedelta(days=7)).astimezone(pytz.timezone("Asia/Tashkent")).date()

#             # now get all productanalytics for that week
#             product_analytics_before = ProductAnalytics.objects.filter(
#                 created_at__date__gte=week_before, created_at__date__lt=first_date, product=product
#             )

#             week_after = (first_date + datetime.timedelta(days=7)).astimezone(pytz.timezone("Asia/Tashkent")).date()

#             product_analytics_after = ProductAnalytics.objects.filter(
#                 created_at__date__gte=first_date, created_at__date__lte=week_after, product=product
#             )

#             return Response(
#                 {
#                     "banner": BannerSerializer(banner).data,
#                     "product_analytics_before": ProductAnalyticsSerializer(product_analytics_before, many=True).data,
#                     "product_analytics_after": ProductAnalyticsSerializer(product_analytics_after, many=True).data,
#                 },
#                 status=status.HTTP_200_OK,
#             )

#         except Exception as e:
#             return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
