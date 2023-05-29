from rest_framework.response import Response
from rest_framework.request import Request
from rest_framework import status, authentication
from rest_framework.decorators import api_view, permission_classes, authentication_classes
from rest_framework.permissions import IsAuthenticated
from django.db.models import Max, Count

from uzum.product.models import Product

from .serializers import CategorySerializer
from .models import Category


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([authentication.TokenAuthentication])
def get_categories_as_tree(request):
    """
    Returns all categories as tree.
    Args:
        request (Request): _description_

    Url: /api/categories/

    Returns:
        Categories: nested dict of categories where each category has a list of its children
    """
    try:

        def category_dict(category: Category):
            return {
                "categoryId": category.categoryId,
                "title": category.title,
                "seo": category.seo,
                "adult": category.adult,
                "created_at": category.created_at,
                "updated_at": category.updated_at,
                "children": [category_dict(child) for child in category.children.all()],
            }

        root_category = Category.objects.get(categoryId=1)
        category_tree = category_dict(root_category)

        return Response(status=status.HTTP_200_OK, data=category_tree)

    except Category.DoesNotExist:
        return Response(status=status.HTTP_404_NOT_FOUND)

    except Exception as e:
        return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([authentication.TokenAuthentication])
def get_category_products_overview(request: Request, category_id):
    """
    Returns products of a category.
    Note: I do not need to add sku to products, because I call this endpoint on categories page
    where I will just show position of products with other fields.
    Args:
        request (Request): _description_
        category_id (_type_): list of products
    """
    try:
        category = Category.objects.get(categoryId=category_id)
        categories = category.get_category_descendants(category, include_self=True)

        products = (
            Product.objects.filter(category__in=categories)
            .values("product_id", "title", "description", "shop__title", "characteristics", "photos")
            .annotate(
                latest_orders_amount=Max("analytics__orders_amount"),
                sku_count=Count("skus"),
            )
            .values(
                "title",
                "description",
                "shop__title",
                "characteristics",
                "photos",
                "latest_orders_amount",
                "sku_count",
                "product_id",
            )
            .order_by("-latest_orders_amount")
        )

        result = sorted(
            [
                {
                    "title": product["title"],
                    "description": product["description"],
                    "shop_title": product["shop__title"],
                    "characteristics": product["characteristics"],
                    "photos": product["photos"],
                    "position_number": position + 1,  # Add 1 to make it 1-based index
                    "sku_count": product["sku_count"],
                }
                for position, product in enumerate(products)
            ],
            key=lambda product: product["position_number"],
        )

        return Response(status=status.HTTP_200_OK, data=result)

    except Exception as e:
        return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)


@api_view(["GET"])
@permission_classes([IsAuthenticated])
@authentication_classes([authentication.TokenAuthentication])
def get_category_analytics(request: Request, category_id):
    """
    Returns analytics of a category.
    Analytics: for each date, number of orders, number of products, amount of sales, number of shops for this category,
    number of reviews, aveage rating of products, number of shops which sold something on that day for this category.
    Args:
        request (Request): _description_
        category_id (_type_): _description_
    """
    try:
        pass
    except Exception as e:
        return Response(status=status.HTTP_500_INTERNAL_SERVER_ERROR)
