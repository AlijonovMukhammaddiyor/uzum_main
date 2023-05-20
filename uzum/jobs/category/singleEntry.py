import traceback
import uuid
from datetime import datetime

from uzum.category.models import Category, CategoryAnalytics


def does_category_exist(categoryId: int):
    return Category.objects.filter(categoryId=categoryId).exists()

def create_category_analytics(categoryId: int, totalProducts: int):
    try:
        print("Creating category analytics...")
        category = Category.objects.get(categoryId=categoryId)
        anaytics = CategoryAnalytics.objects.create(
            category=category,
            totalProducts=totalProducts,
            created_at=datetime.now(),
        )

        return anaytics
    except Exception as e:
        print(f"Error in createCategoryAnalytics: {e}")
        traceback.print_exc()
        return None


def find_category_analytics(categoryId: int):
    try:
        category = Category.objects.get(categoryId=categoryId)
        anaytics = CategoryAnalytics.objects.filter(category=category)

        return anaytics
    except Exception as e:
        print(f"Error in findCategoryAnalytics: {e}")
        return None


def find_category(categoryId: int):
    try:
        category = Category.objects.get(categoryId=categoryId)

        return category
    except Exception as _:
        return None


def create_category(
    categoryId: int,
    title: str = "",
    seo: str = "",
    adult: bool = False,
    parent: uuid = None,
):
    try:
        category = Category.objects.create(
            categoryId=categoryId,
            title=title,
            seo=seo,
            adult=adult,
            parent=parent,
        )

        return category
    except Exception as e:
        print(f"Error in createCategory: {e}")
        return None


# from uzum.category.models import CategoryAnalytics
# >>> from django.db.models import Count
# >>>
# >>> from django.db.models.functions import TruncDate
# >>>
# >>> analytics_count = (
# ...     CategoryAnalytics.objects
# ...     .annotate(day=TruncDate('created_at'))
# ...     .values('day')
# ...     .annotate(count=Count('id'))
# ...     .order_by('day')
# ...
# ... )
# >>> for entry in analytics_count:
# ...     print(f"Date: {entry['day']}, Count: {entry['count']}")
# ...
# Date: 2023-05-19, Count: 6373
# Date: 2023-05-20, Count: 12757
# >>> analytics_to_delete = CategoryAnalytics.objects.exclude(
# ...     id__in=CategoryAnalytics.objects.order_by('created_at')
# ...     .values_list('id', flat=True)[:3200]
# ...     .union(CategoryAnalytics.objects.order_by('-created_at')
# ...     .values_list('id', flat=True)[:3200])
# ... )
# >>> len(analytics_to_delete)
# 12730
# >>> analytics_to_delete.delete()
# (12730, {'category.CategoryAnalytics': 12730})
# >>>
# >>> analytics_count = (
# ...     CategoryAnalytics.objects
# ...     .annotate(day=TruncDate('created_at'))
# ...     .values('day')
# ...     .annotate(count=Count('id'))
# ...     .order_by('day')
# ... )
# >>> for entry in analytics_count:
# ...     print(f"Date: {entry['day']}, Count: {entry['count']}")
