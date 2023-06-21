import datetime

import pytz
from django.db import models
from django.db.models import Avg, F
from django.db.models.functions import TruncDay
from django.db.models import Sum
from django.utils import timezone

from uzum.category.models import Category, CategoryAnalytics
from uzum.product.models import Product, ProductAnalytics
from uzum.shop.models import Shop, ShopAnalytics
from uzum.sku.models import SkuAnalytics


def seconds_until_midnight():
    """Get the number of seconds until midnight."""
    now = timezone.now()
    midnight = now.replace(hour=23, minute=59, second=59, microsecond=999999)
    return (midnight - now).seconds


def get_date_pretty(date: datetime.datetime):
    return date.strftime("%Y-%m-%d")


def calculate_shop_analytics_in_category(
    category: Category, start_date: datetime.datetime, end_date: datetime.datetime
):
    try:
        if start_date < datetime.datetime(2023, 5, 20, 0, 0, 0, 0, pytz.timezone("Asia/Tashkent")):
            start_date = datetime.datetime(2023, 5, 20, 0, 0, 0, 0, pytz.timezone("Asia/Tashkent"))

        shares = []

        categories = Category.get_descendants(category, include_self=True)
        shop_analytics = ShopAnalytics.objects.filter(
            categories__in=categories,
            created_at__range=(start_date, end_date),
        ).order_by("total_orders")

        delta_orders = (
            CategoryAnalytics.objects.get(
                category=category,
                date_pretty=get_date_pretty(end_date),
            ).total_orders
            - CategoryAnalytics.objects.get(
                category=category,
                date_pretty=get_date_pretty(start_date),
            ).total_orders
        )

        # 2. Shop might sell products in multiple categories. So, we need to calculate the share of each shop
        # in the category
        for shop_analytic in shop_analytics:
            # calculate total orders before start_date
            total_orders_before_start_date = (
                ProductAnalytics.objects.filter(
                    shop=shop_analytic.shop,
                    category__in=categories,
                    created_at__lt=start_date,
                ).aggregate(total_orders=Sum("orders_amount"))["total_orders"]
                or 0
            )

            # calculate total orders on end_date
            total_orders_after_end_date = (
                ProductAnalytics.objects.filter(
                    shop=shop_analytic.shop,
                    category__in=categories,
                    created_at=end_date,
                ).aggregate(total_orders=Sum("orders_amount"))["total_orders"]
                or 0
            )

            total_orders = total_orders_after_end_date - total_orders_before_start_date

            # calculate share
            share = total_orders / delta_orders

            shop_average_price_in_category = (
                SkuAnalytics.objects.filter(
                    product__shop=shop_analytic.shop, product__category__in=categories, created_at=end_date
                ).aggregate(average_price=Avg("purchase_price"))["average_price"]
                or 0
            )

            shop_average_price = (
                SkuAnalytics.objects.filter(product__shop=shop_analytic.shop, created_at=end_date).aggregate(
                    average_price=Avg("purchase_price")
                )["average_price"]
                or 0
            )

            products_not_sold = ProductAnalytics.objects.filter(
                shop=shop_analytic.shop, category__in=categories, created_at=end_date, orders_amount=0
            ).count()

            shares.append(
                {
                    "shop_id": shop_analytic.shop.seller_id,
                    "shop_name": shop_analytic.shop.title,
                    "share": share,
                    "shop_orders": total_orders,
                    "shop_total_orders": shop_analytic.total_orders,
                    "shop_total_products": shop_analytic.total_products,
                    "shop_total_reviews": shop_analytic.total_reviews,
                    "shop_rating": shop_analytic.rating,
                    "shop_average_price": shop_average_price,
                    "shop_average_price_in_category": shop_average_price_in_category,
                    "products_not_sold": products_not_sold,
                }
            )

        print("Shares: ", shares)
        return shares

    except Exception as e:
        print("Error in calculate_shop_analytics_in_category: ", e)
        return []


def get_total_orders_for_category(category: Category, start_date: datetime.datetime, end_date: datetime.datetime):
    try:
        total_orders = (
            CategoryAnalytics.objects.filter(category=category, created_at__range=(start_date, end_date))
            .annotate(date=TruncDay("created_at"))
            .values("date", "date_pretty", "total_orders")
            .annotate(total_order=Sum("total_orders"))
            .order_by("date")
        )

        return total_orders

    except Exception as e:
        print("Error in get_total_orders_for_category: ", e)
        return []


def calculate_niche_score_for_category(category: Category, start_date: datetime.datetime, end_date: datetime.datetime):
    # calculate key metrics such as total orders, average orders per day, number of shops, average orders per shop,
    # and average price per item

    # 1. total orders for period
    total_orders = []
    # datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")
    # check if start_date is before 2023 May 20. if it is, then set start_date to 2023 May 20

    if start_date < datetime.datetime(2023, 5, 20, tzinfo=pytz.timezone("Asia/Tashkent")):
        start_date = datetime.datetime(2023, 5, 20, tzinfo=pytz.timezone("Asia/Tashkent"))

    start_pretty = get_date_pretty(start_date)
    end_date = get_date_pretty(end_date)


def average_orders_per_shop(category: Category, start_date: datetime.datetime, end_date: datetime.datetime):
    """
    This function calculates the average orders per shop for each day within the date range for the given category
    Args:
        category (Category): _description_
        start_date (datetime.datetime): should be after 2023 May 20 and timezone should be Asia/Tashkent
        end_date (datetime.datetime): timezone should be Asia/Tashkent

    Returns:
        dict: key is date_pretty and value is average orders per shop for that date
    """
    try:
        if start_date < datetime.datetime(2023, 5, 20, tzinfo=pytz.timezone("Asia/Tashkent")):
            start_date = datetime.datetime(2023, 5, 20, tzinfo=pytz.timezone("Asia/Tashkent"))

        # Calculate average orders per shop for each day within the date range for each category
        category_analytics = CategoryAnalytics.objects.filter(
            category=category, created_at__range=(start_date, end_date)
        ).annotate(average_orders_per_shop=Avg(F("total_orders") / F("total_shops"), output_field=models.FloatField()))

        avg_orders_per_shop_dict = {}

        for ca in category_analytics:
            avg_orders_per_shop_dict[ca.date_pretty] = ca.average_orders_per_shop

        return avg_orders_per_shop_dict

    except Exception as e:
        print("Error in average_orders_per_shop: ", e)
        return {}


def average_price_per_item(category):
    products = category.products.all().annotate(average_price=Avg("skus__purchase_price"))
    average_price_per_item = products.aggregate(Avg("average_price"))["average_price__avg"]

    return average_price_per_item


def get_average_price_per_order(category: Category, start_date: datetime.datetime, end_date: datetime.datetime):
    categories = Category.get_descendants(category, include_self=True)

    # Ensure start_date is not earlier than 2023-05-20
    if start_date < datetime.datetime(2023, 5, 20, tzinfo=pytz.timezone("Asia/Tashkent")):
        start_date = datetime.datetime(2023, 5, 20, tzinfo=pytz.timezone("Asia/Tashkent"))

    # Calculate total orders
    total_orders = (
        CategoryAnalytics.objects.get(category=category, date_pretty=start_date.strftime("%Y-%m-%d")).total_orders
        - CategoryAnalytics.objects.get(category=category, date_pretty=end_date.strftime("%Y-%m-%d")).total_orders
    )

    # Abort if no orders
    if total_orders <= 0:
        return 0

    # Filter products that belong to the category and have orders between the date range
    products_with_orders = Product.objects.filter(
        category__in=categories,
        analytics__created_at__range=(start_date, end_date),
        analytics__orders_amount__gt=0,
    ).distinct()

    # For each product, calculate the average price
    products_with_avg_price = products_with_orders.annotate(
        avg_price=Avg("skus__analytics__purchase_price"),
    )

    # Calculate the average price per order
    total_price = products_with_avg_price.aggregate(total_price=Sum("avg_price"))["total_price"]

    if total_price is None:
        return 0

    return total_price / total_orders


def gini_coefficient(category: Category, date: datetime.datetime):
    """
    This function calculates Gini coefficient for a category on a given date
    Args:
        category (_type_): _description_
        date (datetime.datetime): timezone should be Asia/Tashkent

    Returns:
        float: Gini coefficient for a category on a given date
    """
    # get shops for category

    categories = Category.get_descendants(category, include_self=True)

    shop_analytics = (
        ShopAnalytics.objects.filter(categories__in=categories, date_pretty=date.strftime("%Y-%m-%d"))
        .distinct()
        .order_by("total_orders")
    )

    shop_orders = list(shop_analytics.values_list("total_orders", flat=True))

    n = len(shop_orders)
    if n == 0 or sum(shop_orders) == 0:
        return None

    gini_coefficient = (2 * sum((i + 1) * order for i, order in enumerate(shop_orders)) - n * sum(shop_orders) - 1) / (
        n * sum(shop_orders)
    )
    return gini_coefficient


def HHI(category: Category, date: datetime.datetime):
    """
    This function calculates Herfindahl-Hirschman Index for a category on a given date
    Args:
        category (Category): _description_
        date (datetime.datetime): _description_

    Returns:
        _type_: _description_
    """
    categories = category.get_descendants(include_self=True)
    total_orders = CategoryAnalytics.objects.get(category=category, date_pretty=date.strftime("%Y-%m-%d")).total_orders

    shop_analytics = (
        ShopAnalytics.objects.filter(categories__in=categories, date_pretty=date.strftime("%Y-%m-%d"))
        .distinct()
        .order_by("total_orders")
    )

    shop_market_shares = [(shop.total_orders / total_orders) ** 2 for shop in shop_analytics]

    return sum(shop_market_shares)


def concentration_ratio(category: Category, N, date: datetime.datetime):
    """
    This function calculates concentration ratio for a category
    Args:
        category (_type_): _description_
        N (_type_): _description_

    Returns:
        _type_: _description_
    """
    categories = category.get_descendants(include_self=True)

    shop_analytics = (
        ShopAnalytics.objects.filter(categories__in=categories, date_pretty=date.strftime("%Y-%m-%d"))
        .distinct()
        .order_by("total_orders")
    )

    top_n_shops = shop_analytics[:N]

    top_n_orders = sum(shop.total_orders for shop in top_n_shops)
    total_orders = CategoryAnalytics.objects.get(category=category, date_pretty=date.strftime("%Y-%m-%d")).total_orders

    return top_n_orders / total_orders


def growth_rate(category: Category, date: datetime.datetime, period: int = 7):
    """
    This function calculates growth rate for a category
    Args:
        category (_type_): _description_
        date (datetime.datetime): _description_

    Returns:
        _type_: _description_
    """
    period_ago = date - datetime.timedelta(days=period)
    current_orders = CategoryAnalytics.objects.get(
        category=category, date_pretty=date.strftime("%Y-%m-%d")
    ).total_orders
    try:
        previous_orders = CategoryAnalytics.objects.get(
            category=category, date_pretty=period_ago.strftime("%Y-%m-%d")
        ).total_orders

        return (current_orders - previous_orders) / previous_orders
    except CategoryAnalytics.DoesNotExist:
        # should fix this by adjusting period if there is no data for period_ago
        return 0


def calculate_market_opportunity_index(category: Category, date: datetime.datetime):
    gr = growth_rate(category, date)
    competitiveness_index = calculate_competitiveness_index(category, date)

    if competitiveness_index != 0:
        market_opportunity_index = gr / competitiveness_index
    else:
        market_opportunity_index = 0  # Or some other value indicating undefined/very high opportunity
    return market_opportunity_index


def calculate_competitiveness_index(category: Category, date: datetime.datetime):
    cat_analytics = CategoryAnalytics.objects.get(category=category, date_pretty=date.strftime("%Y-%m-%d"))
    total_shops = cat_analytics.total_shops
    gini_c = gini_coefficient(category, date)

    competitiveness_index = total_shops * (1 - gini_c)

    return competitiveness_index
