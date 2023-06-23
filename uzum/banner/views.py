import datetime
import traceback

import pytz
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from uzum.banner.models import Banner
from uzum.banner.serializers import BannerSerializer

# from uzum.category.utils import seconds_until_midnight
from uzum.product.models import Product, ProductAnalytics, get_today_pretty
from uzum.product.serializers import ProductAnalyticsSerializer, ProductSerializer
from uzum.shop.models import Shop, ShopAnalytics
from uzum.shop.serializers import ShopSerializer
from uzum.sku.models import get_day_before_pretty

# from django.views.decorators.cache import cache_page
# from django.utils.decorators import method_decorator


# @method_decorator(cache_page(seconds_until_midnight()), name="get")
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
            banners = Banner.objects.all().order_by("link")
            products = (
                Product.objects.filter(analytics__banners__in=banners)
                .distinct()
                .values("product_id", "title", "description", "photos")
            ).order_by("title")

            return Response(
                {"banners": BannerSerializer(banners, many=True).data, "products": products},
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            traceback.print_exc()
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# @method_decorator(cache_page(seconds_until_midnight()), name="get")
class OngoingBannersView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    serializer_class = BannerSerializer

    @extend_schema(tags=["Banner"])
    def get(self, request):
        try:
            banners = Banner.objects.all()
            date_pretty = get_today_pretty()
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


class BannerImpactView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [JWTAuthentication]
    allowed_methods = ["GET"]
    serializer_class = BannerSerializer

    @extend_schema(tags=["Banner"])
    def get(self, request, banner_id: str):
        try:
            banner = Banner.objects.get(id=banner_id)

            analytics = banner.productanalytics_set.all()

            if len(analytics) == 0:
                return Response({"error": "No analytics found for this banner"}, status=status.HTTP_404_NOT_FOUND)

            product = analytics[0].product

            # get first day banner was used with productanalytics
            first_date: datetime = analytics.order_by("created_at")[0].created_at

            # now get week before in Asia/Tashkent timezone
            week_before = (first_date - datetime.timedelta(days=7)).astimezone(pytz.timezone("Asia/Tashkent")).date()

            # now get all productanalytics for that week
            product_analytics_before = ProductAnalytics.objects.filter(
                created_at__date__gte=week_before, created_at__date__lt=first_date, product=product
            )

            week_after = (first_date + datetime.timedelta(days=7)).astimezone(pytz.timezone("Asia/Tashkent")).date()

            product_analytics_after = ProductAnalytics.objects.filter(
                created_at__date__gte=first_date, created_at__date__lte=week_after, product=product
            )

            return Response(
                {
                    "banner": BannerSerializer(banner).data,
                    "product_analytics_before": ProductAnalyticsSerializer(product_analytics_before, many=True).data,
                    "product_analytics_after": ProductAnalyticsSerializer(product_analytics_after, many=True).data,
                },
                status=status.HTTP_200_OK,
            )

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
