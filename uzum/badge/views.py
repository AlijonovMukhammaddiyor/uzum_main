from datetime import datetime

from django.db.models import F
from django.db.models.functions import TruncDate
from django.db.models import Max

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework import permissions, authentication
from uzum.product.serializers import ProductAnalyticsSerializer

from uzum.utils.general import decode_request
from uzum.product.models import ProductAnalytics, Product

from .models import Badge
from .serializers import BadgeSerializer


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([authentication.TokenAuthentication])
def get_badges(request: Request):
    """
    Returns all badges.
    Args:
        request (_type_):

    Url: /api/badges/

    Returns:
        Badges: serialized badges
    """
    try:
        badges = Badge.objects.all()

        serializer = BadgeSerializer(badges, many=True)

        return Response(status=200, data=serializer.data)

    except Badge.DoesNotExist:
        return Response(status=404)

    except Exception as e:
        return Response(status=500)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([authentication.TokenAuthentication])
def get_badge(request: Request, badge_id):
    """
    Returns badge by id.
    Args:
        request (Request): _description_
        badge_id (int): badge id

    Url: /api/badges/<int:badge_id>/

    Returns:
        Badge: serialized badge
    """
    try:
        badge = Badge.objects.get(badge_id=badge_id)

        serializer = BadgeSerializer(badge)

        return Response(status=200, data=serializer.data)

    except Badge.DoesNotExist:
        return Response(status=404)

    except Exception as e:
        return Response(status=500)


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
@authentication_classes([authentication.TokenAuthentication])
def get_all_products_with_badge(request: Request, badge_id: int):
    """
    Returns all products with badge.

    Url: /api/badges/<int:badge_id>/products/

    Args:
        request (Request): _description_
        badge_id (int): _description_
    """
    try:
        payload = decode_request(request, "GET")

        date = payload.get("start_date", None)

        if date:
            date = datetime.fromtimestamp(int(date)).strftime("%Y-%m-%d")
            # products have ManyToMany relation with badges
            products = ProductAnalytics.objects.filter(badges__badge_id=badge_id, date_pretty=date)
        else:
            result = (
                Product.objects.filter(analytics__badges__badge_id=badge_id)
                .values(
                    "product_id",
                    "created_at",
                    "title",
                    "description",
                    "shop_id",
                    "category_id",
                    "analytics__created_at",
                    "analytics__banners__id",
                    "analytics__badges__badge_id",
                    "analytics__reviews_amount",
                    "analytics__rating",
                    "analytics__orders_amount",
                )
                .annotate(
                    banners=F("analytics__banners"),
                    badges=F("analytics__badges"),
                )
                .order_by("-analytics__created_at")
                .values(
                    "product_id",
                    "created_at",
                    "title",
                    "description",
                    "shop_id",
                    "category_id",
                    "analytics__created_at",
                    "banners",
                    "badges",
                    "analytics__reviews_amount",
                    "analytics__rating",
                    "analytics__orders_amount",
                )
            )

            products = []

            result_list = [
                {
                    "product_id": item["product_id"],
                    "created_at": item["created_at"],
                    "title": item["title"],
                    "description": item["description"],
                    "shop_id": item["shop_id"],
                    "category_id": item["category_id"],
                    ""
                    "analytics": {
                        "created_at": item["analytics__created_at"],
                        "banners": [banner["id"] for banner in item["banners"]],
                        "badges": [badge["badge_id"] for badge in item["badges"]],
                        "reviews_amount": item["analytics__reviews_amount"],
                        "rating": item["analytics__rating"],
                        "orders_amount": item["analytics__orders_amount"],
                    },
                }
                for item in result
            ]

        serializer = ProductAnalyticsSerializer(products, many=True)

    except Exception as e:
        return Response(status=500)
