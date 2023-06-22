import datetime
import traceback

from drf_spectacular.utils import extend_schema
import pytz
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.pagination import PageNumberPagination
from rest_framework import permissions
from uzum.product.serializers import ProductAnalyticsSerializer, ProductSerializer
from rest_framework_simplejwt import authentication
from uzum.product.models import ProductAnalytics, Product, get_today_pretty

from .models import Badge
from .serializers import BadgeSerializer


class AllBadgesView(APIView):
    """
    Returns all badges.
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.JWTAuthentication]
    allowed_methods = ["GET"]
    serializer_class = BadgeSerializer

    @extend_schema(tags=["Badges"])
    def get(self, request: Request):
        try:
            badges = Badge.objects.all()

            serializer = BadgeSerializer(badges, many=True)

            return Response(status=200, data=serializer.data)

        except Badge.DoesNotExist:
            return Response(status=404, data={"message": "Badge not found"})

        except Exception as e:
            return Response(status=500, data={"message": str(e)})


class OngoingBadgesView(APIView):
    """
    Returns ongoing badges.
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.JWTAuthentication]
    allowed_methods = ["GET"]
    serializer_class = BadgeSerializer

    @extend_schema(tags=["Badges"])
    def get(self, request: Request):
        try:
            # only way to get ongoing badges is to filter by recent product analytics badges field
            # product analytics have many to many relationship with badges

            date_str = request.query_params.get("date", None)
            date_str = date_str if date_str else get_today_pretty()

            badges = []

            recent_product_analytics = ProductAnalytics.objects.filter(date_pretty=date_str)

            print(recent_product_analytics.count())

            # Get distinct badges
            badges = Badge.objects.filter(products__in=recent_product_analytics).distinct()

            # Serialize the badges
            serializer = BadgeSerializer(badges, many=True)

            return Response(status=200, data=serializer.data)

        except Badge.DoesNotExist:
            return Response(status=404, data={"message": "Badge not found"})

        except Exception as e:
            return Response(status=500, data={"message": str(e)})


class BadgeProducts(APIView):
    """
    Returns products of a badge.
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.JWTAuthentication]
    allowed_methods = ["GET"]
    serializer_class = ProductAnalyticsSerializer
    pagination_class = PageNumberPagination

    @extend_schema(tags=["Badges"])
    def get(self, request: Request, badge_id: int):
        try:
            badge = Badge.objects.get(badge_id=badge_id)
            products = Product.objects.filter(analytics__badges=badge)
            paginator = PageNumberPagination()

            page = paginator.paginate_queryset(products, request)

            serializer = ProductSerializer(page, many=True)

            return paginator.get_paginated_response(serializer.data)

        except Badge.DoesNotExist:
            return Response(status=404, data={"message": "Badge not found"})

        except Exception as e:
            traceback.print_exc()
            return Response(status=500, data={"message": str(e)})


class BadgeAnalytics(APIView):
    """
    Returns analytics of a badge.
    """

    permission_classes = [permissions.IsAuthenticated]
    authentication_classes = [authentication.JWTAuthentication]
    allowed_methods = ["GET"]
    serializer_class = ProductAnalyticsSerializer
    pagination_class = PageNumberPagination

    @extend_schema(tags=["Badges"])
    def get(self, request: Request, badge_id: int):
        try:
            badge = Badge.objects.get(badge_id=badge_id)
            print(Product.objects.all().count())
            products_count = ProductAnalytics.objects.filter(badges=badge, date_pretty=get_today_pretty()).count()
            print(products_count)
            last_product_analytics = (
                ProductAnalytics.objects.filter(badges=badge).order_by("-created_at").first().date_pretty
            )

            # now, get thelatest product analytics and compare the date_pretty field
            latest_date_pretty = ProductAnalytics.objects.order_by("-created_at").first().date_pretty

            res = {
                "products_count": products_count,
                "badge": BadgeSerializer(badge).data,
                "is_finished": last_product_analytics != latest_date_pretty,
                "latest_date": last_product_analytics,
            }

            return Response(status=200, data=res)

        except Badge.DoesNotExist:
            return Response(status=404, data={"message": "Badge not found"})

        except Exception as e:
            traceback.print_exc()
            return Response(status=500, data={"message": str(e)})
