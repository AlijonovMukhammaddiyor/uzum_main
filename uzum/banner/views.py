import traceback
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework.authentication import TokenAuthentication
from uzum.banner.models import Banner
from rest_framework import status

from uzum.banner.serializers import BannerSerializer
from uzum.product.models import Product, ProductAnalytics, get_today_pretty
from uzum.product.serializers import ProductSerializer
from uzum.shop.models import Shop, ShopAnalytics
from uzum.shop.serializers import ShopSerializer
from uzum.sku.models import get_day_before_pretty


class BannersView(APIView):
    """
    Get all banners with product analytics
    """

    permission_classes = [IsAuthenticated]
    authentication_classes = [TokenAuthentication]
    allowed_methods = ["GET"]
    serializer_class = BannerSerializer

    def get(self, request):
        try:
            banners = Banner.objects.all()
            res = []

            for banner in banners:
                data = BannerSerializer(banner).data
                link = banner.link
                if "/product/" in link:
                    # append product details if link contains '/product/'
                    product_analytics = ProductAnalytics.objects.filter(banners=banner)
                    print("product_analytics: ", product_analytics, "link: ", link)
                    if product_analytics.exists():
                        product = product_analytics.first().product
                        product_data = ProductSerializer(product).data
                        print("product_data is added")
                        data["product"] = product_data

                elif link and len(link.split("/")) == 4:
                    shop_name = link.split("/")[3]
                    shop = Shop.objects.filter(title=shop_name)
                    if shop.exists():
                        shop_data = ShopSerializer(shop.first()).data
                        data["shop"] = shop_data

                res.append(data)

            return Response(res, status=status.HTTP_200_OK)

        except Exception as e:
            traceback.print_exc()
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
