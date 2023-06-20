from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from uzum.banner.models import Banner
from rest_framework import status

from uzum.banner.serializers import BannerSerializer
from uzum.product.models import ProductAnalytics, get_today_pretty
from uzum.sku.models import get_day_before_pretty


class BannersView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    allowed_methods = ["GET"]
    serializer_class = BannerSerializer

    def get(self, request):
        try:
            banners = Banner.objects.filter(link__icontains="product")
            banner = Banner.objects.get(id="3b0d4f03-0dd2-4126-9e4d-1b656d0ce1fa")

            print(banner.link)

            analytics = banner.productanalytics_set.all()

            for a in analytics:
                print(a.product.title, a.date_pretty)

            res = []

            for banner in banners:
                if banner.link:
                    res.append(BannerSerializer(banner).data)

            # serializer = BannerSerializer(banners, many=True)
            return Response(res, status=status.HTTP_200_OK)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class OngoingBannersView(APIView):
    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    allowed_methods = ["GET"]
    serializer_class = BannerSerializer

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
