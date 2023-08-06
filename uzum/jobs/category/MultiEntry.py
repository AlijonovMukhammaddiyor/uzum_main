import traceback

from uzum.category.models import Category, CategoryAnalytics
from uzum.jobs.category.utils import get_categories_tree
from uzum.utils.general import get_today_pretty


def get_all_categories():
    try:
        return Category.objects.all().order_by("categoryId")
    except Exception as e:
        print(f"Error in get_all_categories: {e}")
        return None


def create_categories(categories):
    try:
        result = Category.objects.bulk_create(categories, ignore_conflicts=True)
        print(f"createCategories: {len(result)} objects inserted, {len(categories) - len(result)} objects skipped")
        return result
    except Exception as e:
        print(f"Error in createCategories: {e}")
        return None


def create_category_analytics_bulk(analytics):
    try:
        result = CategoryAnalytics.objects.bulk_create(analytics, ignore_conflicts=True)
        print(
            f"createCategoryAnalytics: {len(result)} objects inserted, {len(analytics) - len(result)} objects skipped"
        )
        return result
    except Exception as e:
        print(f"Error in createCategoryAnalyticsBulk: {e}")
        return None


def get_categories_with_less_than_n_products(n):
    """
    Get categories with less than n products
    Args:
        n (int):   number of products
    Returns:
        Array: [{
                categoryId: total_products
            }]
    """
    try:
        # all_categories = sync_to_async(Category.objects.all().order_by("categoryId"))
        # order_by("categoryId")
        all_category_analytics = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty()).order_by(
            "category__categoryId"
        )
        print(
            f"getCategoriesWithLessThanNProducts: all category analytics fetched {len(all_category_analytics)}",
        )
        # 1. make dict of all categories: key - categoryId, value - total_products and children
        # children is ManyToManey field to itself. We need to get list children's categoryId
        all_categories_dict = {}

        for category in all_category_analytics:
            all_categories_dict[category.category.categoryId] = {
                "categoryId": category.category.categoryId,
                "total_products": category.total_products,
                "children": list(category.category.child_categories.values_list("categoryId", flat=True)),
            }

        filtered_categories = []

        filter_categories(all_categories_dict[1], all_categories_dict, filtered_categories, n, {})

        print(f"getCategoriesWithLessThanNProducts: {len(filtered_categories)} categories found")

        # calculate total products for all filtered categories
        total = 0
        for category in filtered_categories:
            total += category["total_products"]

        print(f"getCategoriesWithLessThanNProducts: {total} products found")

        return filtered_categories
    except Exception as e:
        print(f"Error in getCategoriesWithLessThanNProducts: {e}")
        print(traceback.print_exc())
        return None


def filter_categories(current: dict, categories_dict: dict, categories_list: list[dict], n, memo={}):
    try:
        if not current:
            return

        if current["total_products"] < n or len(current["children"]) == 0:
            categories_list.append(current)
            return

        for child in current["children"]:
            try:
                filter_categories(categories_dict[child], categories_dict, categories_list, n, memo)
            except KeyError:
                print(f"KeyError in filter_categories: {child}")
                traceback.print_exc()
                continue

        return
    except Exception as e:
        print(f"Error in filter_categories: {e}")
        traceback.print_exc()
        return None


def get_categories_with_less_than_n_products_for_russian_title(n, cat_totals: dict):
    """
    Get categories with less than n products
    Args:
        n (int):   number of products
    Returns:
        Array: [{
                categoryId: total_products
            }]
    """
    try:
        # all_categories = sync_to_async(Category.objects.all().order_by("categoryId"))
        # order_by("categoryId")
        all_category_analytics = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty()).order_by(
            "category__categoryId"
        )
        print(
            f"getCategoriesWithLessThanNProducts: all category analytics fetched {len(all_category_analytics)}",
        )
        # 1. make dict of all categories: key - categoryId, value - total_products and children
        # children is ManyToManey field to itself. We need to get list children's categoryId
        all_categories_dict = {}

        for category in all_category_analytics:
            if category.category.categoryId not in cat_totals:
                continue
            all_categories_dict[category.category.categoryId] = {
                "categoryId": category.category.categoryId,
                "total_products": cat_totals[category.category.categoryId],
                "children": list(category.category.child_categories.values_list("categoryId", flat=True)),
            }

        filtered_categories = []

        filter_categories(all_categories_dict[1], all_categories_dict, filtered_categories, n, {})

        print(f"getCategoriesWithLessThanNProducts: {len(filtered_categories)} categories found")

        # calculate total products for all filtered categories
        total = 0
        for category in filtered_categories:
            total += category["total_products"]

        print(f"getCategoriesWithLessThanNProducts: {total} products found")

        return filtered_categories
    except Exception as e:
        print(f"Error in getCategoriesWithLessThanNProducts for title: {e}")
        print(traceback.print_exc())
        return None


def get_categories_with_less_than_n_products2(n):
    """
    Get categories with less than n products
    Args:
        n (int):   number of products
    Returns:
        Array: [{
                categoryId: total_products
            }]
    """
    try:
        # all_categories = sync_to_async(Category.objects.all().order_by("categoryId"))
        # order_by("categoryId")
        all_category_analytics = CategoryAnalytics.objects.filter(date_pretty=get_today_pretty()).order_by(
            "category__categoryId"
        )
        print(
            f"getCategoriesWithLessThanNProducts: all category analytics fetched {len(all_category_analytics)}",
        )
        category_tree = get_categories_tree()
        cat_dict = {category["category"]["id"]: category["total"] for category in category_tree}

        # 1. make dict of all categories: key - categoryId, value - total_products and children
        # children is ManyToManey field to itself. We need to get list children's categoryId
        all_categories_dict = {}

        for category in all_category_analytics:
            all_categories_dict[category.category.categoryId] = {
                "categoryId": category.category.categoryId,
                "total_products": cat_dict[category.category.categoryId]
                if category.category.categoryId in cat_dict
                else 0,
                "children": list(category.category.child_categories.values_list("categoryId", flat=True)),
            }

        filtered_categories = []

        filter_categories(all_categories_dict[1], all_categories_dict, filtered_categories, n, {})

        print(f"getCategoriesWithLessThanNProducts: {len(filtered_categories)} categories found")

        # calculate total products for all filtered categories
        total = 0
        for category in filtered_categories:
            total += category["total_products"]

        print(f"getCategoriesWithLessThanNProducts: {total} products found")

        return filtered_categories
    except Exception as e:
        print(f"Error in getCategoriesWithLessThanNProducts: {e}")
        print(traceback.print_exc())
        return None
