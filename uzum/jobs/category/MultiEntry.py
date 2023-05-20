import traceback

from uzum.category.models import Category, CategoryAnalytics
from asgiref.sync import sync_to_async


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
        print(analytics)
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
        all_categories = get_all_categories()
        # all_categories = []
        print(
            f"getCategoriesWithLessThanNProducts: all categories fetched {len(all_categories)}",
        )
        # 1. make dict of all categories: key - categoryId, value - totalProducts and children
        # children is ManyToManey field to itself. We need to get list children's categoryId
        all_categories_dict = {}

        for category in all_categories:
            # get most recently creted analytics
            try:
                most_recent_analytics = CategoryAnalytics.objects.filter(category=category).latest("created_at")
            except Exception as e:
                print(
                    f"get_categories_with_less_than_n_products: {category.categoryId} - {e}"
                )
                continue

            all_categories_dict[category.categoryId] = {
                "categoryId": category.categoryId,
                "totalProducts": most_recent_analytics.totalProducts,
                "children": list(category.children.values_list("categoryId", flat=True)),
            }

        filtered_categories = []

        filter_categories(all_categories_dict[1], all_categories_dict, filtered_categories, n, {})

        print(f"getCategoriesWithLessThanNProducts: {len(filtered_categories)} categories found")

        # calculate total products for all filtered categories
        total = 0
        for category in filtered_categories:
            total += category["totalProducts"]

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

        if current["totalProducts"] < n or len(current["children"]) == 0:
            categories_list.append(current)
            return

        for child in current["children"]:
            filter_categories(categories_dict[child], categories_dict, categories_list, n, memo)

        return
    except Exception as e:
        print(f"Error in filter_categories: {e}")
        traceback.print_exc()
        return None
