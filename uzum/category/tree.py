import traceback
from datetime import datetime, timedelta

import pytz
from django.core.cache import cache
from django.db import connection

from uzum.category.models import Category, CategoryAnalytics
from uzum.utils.general import get_today_pretty


def update_category_tree(date_pretty=get_today_pretty()):
    categories = Category.objects.filter(categoryanalytics__date_pretty=date_pretty).values(
        "categoryId", "title", "title_ru", "parent_id"
    )

    # first create a dictionary mapping ids to category data
    category_dict = {category["categoryId"]: category for category in categories}

    # then build a mapping from parent_id to a list of its children
    children_map = {}
    for category in categories:
        children_map.setdefault(category["parent_id"], []).append(category)

    # recursive function to build the tree
    def build_tree(category_id):
        category = category_dict[category_id]
        children = children_map.get(category_id, [])
        return {
            "categoryId": category_id,
            "title": category["title"],
            "title_ru": category["title_ru"],
            "children": [build_tree(child["categoryId"]) for child in children],
        }

    # build the tree starting from the root
    category_tree = build_tree(1)
    # store in cache
    cache.set("category_tree", category_tree, timeout=60 * 60 * 48)  # 48 hours
    # return category_tree


def fetch_latest_analytics(date):
    with connection.cursor() as cursor:
        # Create the materialized view
        cursor.execute(
            f"""
            SELECT DISTINCT ON (category_id) category_id,
                total_orders_amount,
                total_orders,
                total_products,
                total_reviews,
                total_shops
            FROM category_categoryanalytics
            WHERE created_at <= '{date}'
            ORDER BY category_id, created_at DESC
        """
        )

        columns = [col[0] for col in cursor.description]

        # Fetch all rows
        rows = cursor.fetchall()

    # Convert query results to list of dictionaries
    analytics_data = [dict(zip(columns, row)) for row in rows]

    return {data["category_id"]: data for data in analytics_data}


def update_category_tree_with_weekly_data(date_pretty=get_today_pretty()):
    if date_pretty is None:
        date_pretty = get_today_pretty()
    try:
        categories = Category.objects.filter(
            categoryanalytics__date_pretty=date_pretty,
        ).values("categoryId", "title", "title_ru", "parent_id")

        # first create a dictionary mapping ids to category data
        category_dict = {category["categoryId"]: category for category in categories}

        # then build a mapping from parent_id to a list of its children
        children_map = {}
        for category in categories:
            children_map.setdefault(category["parent_id"], []).append(category)

        # get analytics data
        analytics_data = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty()).values(
            "category_id",
            "total_orders_amount",
            "total_orders",
            "total_products",
            "total_reviews",
            "total_shops",
        )
        analytics_dict = {data["category_id"]: data for data in analytics_data}

        thirty_days_ago = (datetime.now(tz=pytz.timezone("Asia/Tashkent")) - timedelta(days=7)).replace(
            hour=0, minute=0, second=59, microsecond=0
        )
        monthly_analytics_data = fetch_latest_analytics(thirty_days_ago)

        for data in analytics_dict.values():
            monthly_data = monthly_analytics_data.get(data["category_id"], {})
            # if not monthly_data:
                # print("No monthly data for category: ", data["category_id"])
            for key in ["total_orders_amount", "total_orders", "total_products", "total_reviews", "total_shops"]:
                data[key] = data.get(key, 0) - monthly_data.get(key, 0)

        min_max_data = CategoryAnalytics.objects.filter(
            date_pretty=get_today_pretty(), category__child_categories=None
        ).values(
            "category_id",
            "total_orders_amount",
            "total_orders",
            "total_products",
            "total_reviews",
            "total_shops",
        )

        min_max_dict = {data["category_id"]: data for data in min_max_data}

        for data in min_max_dict.values():
            monthly_data = monthly_analytics_data.get(data["category_id"], {})
            # if not monthly_data:
            #     print("No monthly data for category: ", data["category_id"])
            for key in ["total_orders_amount", "total_orders", "total_products", "total_reviews", "total_shops"]:
                data[key] = data.get(key, 0) - monthly_data.get(key, 0)

        # get min and max values for each type of analytics
        min_max = {
            "total_orders_amount": {
                "min": max(0, min([data["total_orders_amount"] for data in min_max_dict.values()])),
                "max": max([data["total_orders_amount"] for data in min_max_dict.values()]),
            },
            "total_orders": {
                "min": max(0, min([data["total_orders"] for data in min_max_dict.values()])),
                "max": max([data["total_orders"] for data in min_max_dict.values()]),
            },
            "total_reviews": {
                "min": max(0, min([data["total_reviews"] for data in min_max_dict.values()])),
                "max": max([data["total_reviews"] for data in min_max_dict.values()]),
            },
            "total_shops": {
                "min": max(0, min([data["total_shops"] for data in min_max_dict.values()])),
                "max": max([data["total_shops"] for data in min_max_dict.values()]),
            },
            "total_products": {
                "min": max(0, min([data["total_products"] for data in min_max_dict.values()])),
                "max": max([data["total_products"] for data in min_max_dict.values()]),
            },
        }

        # create a dictionary mapping category_id to analytics data
        # recursive function to build the tree
        def build_tree(category_id, type):
            category = category_dict[category_id]
            analytics = analytics_dict.get(category_id, {})
            children = children_map.get(category_id, [])
            res = {
                "categoryId": category_id,
                "title": category["title"],
                "title_ru": category["title_ru"],
                "analytics": analytics.get(type, 0),
                "children": [build_tree(child["categoryId"], type) for child in children],
            }

            # if children is empty remove it
            if len(res["children"]) == 0:
                del res["children"]
            return res

        category_tree_revenue = build_tree(1, type="total_orders_amount")
        category_tree_orders = build_tree(1, type="total_orders")
        category_tree_reviews = build_tree(1, type="total_reviews")
        category_tree_shops = build_tree(1, type="total_shops")
        category_tree_products = build_tree(1, type="total_products")

        # store in cache
        # cache.set("category_tree_data", category_tree, timeout=60 * 60 * 48)  # 48 hours
        # print("revenue tree: ", category_tree_revenue)

        cache.set(
            "category_tree_weekly_revenue",
            {"data": category_tree_revenue, "min_max": min_max["total_orders_amount"]},
            timeout=60 * 60 * 48,
        )  # 48 hours

        cache.set(
            "category_tree_weekly_orders",
            {"data": category_tree_orders, "min_max": min_max["total_orders"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_weekly_reviews",
            {"data": category_tree_reviews, "min_max": min_max["total_reviews"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_weekly_shops",
            {"data": category_tree_shops, "min_max": min_max["total_shops"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_weekly_products",
            {"data": category_tree_products, "min_max": min_max["total_products"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
    except Exception as e:
        print("Error in update_category_tree_with_weekly_data: ", e)
        traceback.print_exc()
        return None


def update_category_tree_with_monthly_data(date_pretty=None):
    if date_pretty is None:
        date_pretty = get_today_pretty()
    try:
        categories = Category.objects.filter(
            categoryanalytics__date_pretty=date_pretty,
        ).values("categoryId", "title", "title_ru", "parent_id")

        # first create a dictionary mapping ids to category data
        category_dict = {category["categoryId"]: category for category in categories}

        # then build a mapping from parent_id to a list of its children
        children_map = {}
        for category in categories:
            children_map.setdefault(category["parent_id"], []).append(category)

        # get analytics data
        analytics_data = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty()).values(
            "category_id",
            "total_orders_amount",
            "total_orders",
            "total_products",
            "total_reviews",
            "total_shops",
        )
        analytics_dict = {data["category_id"]: data for data in analytics_data}

        thirty_days_ago = (datetime.now(tz=pytz.timezone("Asia/Tashkent")) - timedelta(days=30)).replace(
            hour=0, minute=0, second=59, microsecond=0
        )
        monthly_analytics_data = fetch_latest_analytics(thirty_days_ago)

        for data in analytics_dict.values():
            monthly_data = monthly_analytics_data.get(data["category_id"], {})
            # if not monthly_data:
            #     print("No monthly data for category: ", data["category_id"])
            for key in ["total_orders_amount", "total_orders", "total_products", "total_reviews", "total_shops"]:
                data[key] = data.get(key, 0) - monthly_data.get(key, 0)

        min_max_data = CategoryAnalytics.objects.filter(
            date_pretty=get_today_pretty(), category__child_categories=None
        ).values(
            "category_id",
            "total_orders_amount",
            "total_orders",
            "total_products",
            "total_reviews",
            "total_shops",
        )

        min_max_dict = {data["category_id"]: data for data in min_max_data}

        for data in min_max_dict.values():
            monthly_data = monthly_analytics_data.get(data["category_id"], {})
            # if not monthly_data:
            #     print("No monthly data for category: ", data["category_id"])
            for key in ["total_orders_amount", "total_orders", "total_products", "total_reviews", "total_shops"]:
                data[key] = data.get(key, 0) - monthly_data.get(key, 0)

        # get min and max values for each type of analytics
        min_max = {
            "total_orders_amount": {
                "min": max(0, min([data["total_orders_amount"] for data in min_max_dict.values()])),
                "max": max([data["total_orders_amount"] for data in min_max_dict.values()]),
            },
            "total_orders": {
                "min": max(0, min([data["total_orders"] for data in min_max_dict.values()])),
                "max": max([data["total_orders"] for data in min_max_dict.values()]),
            },
            "total_reviews": {
                "min": max(0, min([data["total_reviews"] for data in min_max_dict.values()])),
                "max": max([data["total_reviews"] for data in min_max_dict.values()]),
            },
            "total_shops": {
                "min": max(0, min([data["total_shops"] for data in min_max_dict.values()])),
                "max": max([data["total_shops"] for data in min_max_dict.values()]),
            },
            "total_products": {
                "min": max(0, min([data["total_products"] for data in min_max_dict.values()])),
                "max": max([data["total_products"] for data in min_max_dict.values()]),
            },
        }

        # create a dictionary mapping category_id to analytics data
        # recursive function to build the tree
        def build_tree(category_id, type):
            category = category_dict[category_id]
            analytics = analytics_dict.get(category_id, {})
            children = children_map.get(category_id, [])
            res = {
                "categoryId": category_id,
                "title": category["title"],
                "title_ru": category["title_ru"],
                "analytics": analytics.get(type, 0),
                "children": [build_tree(child["categoryId"], type) for child in children],
            }

            # if children is empty remove it
            if len(res["children"]) == 0:
                del res["children"]
            return res

        category_tree_revenue = build_tree(1, type="total_orders_amount")
        category_tree_orders = build_tree(1, type="total_orders")
        category_tree_reviews = build_tree(1, type="total_reviews")
        category_tree_shops = build_tree(1, type="total_shops")
        category_tree_products = build_tree(1, type="total_products")

        # store in cache
        # cache.set("category_tree_data", category_tree, timeout=60 * 60 * 48)  # 48 hours
        # print("revenue tree: ", category_tree_revenue)

        cache.set(
            "category_tree_monthly_revenue",
            {"data": category_tree_revenue, "min_max": min_max["total_orders_amount"]},
            timeout=60 * 60 * 48,
        )  # 48 hours

        cache.set(
            "category_tree_monthly_orders",
            {"data": category_tree_orders, "min_max": min_max["total_orders"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_monthly_reviews",
            {"data": category_tree_reviews, "min_max": min_max["total_reviews"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_monthly_shops",
            {"data": category_tree_shops, "min_max": min_max["total_shops"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
        cache.set(
            "category_tree_monthly_products",
            {"data": category_tree_products, "min_max": min_max["total_products"]},
            timeout=60 * 60 * 48,
        )  # 48 hours
    except Exception as e:
        print("Error in update_category_tree_with_monthly_data:", e)
        traceback.print_exc()


def update_category_tree_with_data(date_pretty=get_today_pretty()):
    categories = Category.objects.filter(
        categoryanalytics__date_pretty=date_pretty,
    ).values("categoryId", "title", "title_ru", "parent_id")

    # first create a dictionary mapping ids to category data
    category_dict = {category["categoryId"]: category for category in categories}

    # then build a mapping from parent_id to a list of its children
    children_map = {}
    for category in categories:
        children_map.setdefault(category["parent_id"], []).append(category)

    # get analytics data
    analytics_data = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty()).values(
        "category_id",
        "total_orders_amount",
        "total_orders",
        "total_products",
        "total_reviews",
        "total_shops",
    )

    min_max_data = CategoryAnalytics.objects.filter(
        date_pretty=get_today_pretty(), category__child_categories=None
    ).values(
        "category_id",
        "total_orders_amount",
        "total_orders",
        "total_products",
        "total_reviews",
        "total_shops",
    )

    # get min and max values for each type of analytics
    min_max = {
        "total_orders_amount": {
            "min": min([data["total_orders_amount"] for data in min_max_data]),
            "max": max([data["total_orders_amount"] for data in min_max_data]),
        },
        "total_orders": {
            "min": min([data["total_orders"] for data in min_max_data]),
            "max": max([data["total_orders"] for data in min_max_data]),
        },
        "total_reviews": {
            "min": min([data["total_reviews"] for data in min_max_data]),
            "max": max([data["total_reviews"] for data in min_max_data]),
        },
        "total_shops": {
            "min": min([data["total_shops"] for data in min_max_data]),
            "max": max([data["total_shops"] for data in min_max_data]),
        },
        "total_products": {
            "min": min([data["total_products"] for data in min_max_data]),
            "max": max([data["total_products"] for data in min_max_data]),
        },
    }

    # create a dictionary mapping category_id to analytics data
    analytics_dict = {data["category_id"]: data for data in analytics_data}

    # recursive function to build the tree
    def build_tree(category_id, type):
        category = category_dict[category_id]
        analytics = analytics_dict.get(category_id, {})
        children = children_map.get(category_id, [])
        res = {
            "categoryId": category_id,
            "title": category["title"],
            "title_ru": category["title_ru"],
            "analytics": analytics.get(type, 0),
            "children": [build_tree(child["categoryId"], type) for child in children],
        }

        # if children is empty remove it
        if len(res["children"]) == 0:
            del res["children"]
        return res

    # build the tree starting from the root
    category_tree_revenue = build_tree(1, type="total_orders_amount")
    category_tree_orders = build_tree(1, type="total_orders")
    category_tree_reviews = build_tree(1, type="total_reviews")
    category_tree_shops = build_tree(1, type="total_shops")
    category_tree_products = build_tree(1, type="total_products")

    # store in cache
    # cache.set("category_tree_data", category_tree, timeout=60 * 60 * 48)  # 48 hours
    # print("revenue tree: ", category_tree_revenue)

    cache.set(
        "category_tree_revenue",
        {"data": category_tree_revenue, "min_max": min_max["total_orders_amount"]},
        timeout=60 * 60 * 48,
    )  # 48 hours

    cache.set(
        "category_tree_orders",
        {"data": category_tree_orders, "min_max": min_max["total_orders"]},
        timeout=60 * 60 * 48,
    )  # 48 hours
    cache.set(
        "category_tree_reviews",
        {"data": category_tree_reviews, "min_max": min_max["total_reviews"]},
        timeout=60 * 60 * 48,
    )  # 48 hours
    cache.set(
        "category_tree_shops", {"data": category_tree_shops, "min_max": min_max["total_shops"]}, timeout=60 * 60 * 48
    )  # 48 hours
    cache.set(
        "category_tree_products",
        {"data": category_tree_products, "min_max": min_max["total_products"]},
        timeout=60 * 60 * 48,
    )  # 48 hours
