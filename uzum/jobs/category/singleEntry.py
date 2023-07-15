import traceback
import uuid
from datetime import datetime

import pytz

from uzum.category.models import Category, CategoryAnalytics


def does_category_exist(categoryId: int):
    return Category.objects.filter(categoryId=categoryId).exists()


def create_category_analytics(categoryId: int, total_products: int):
    try:
        print("Creating category analytics...")
        category = Category.objects.get(categoryId=categoryId)
        anaytics = CategoryAnalytics.objects.create(
            category=category,
            total_products=total_products,
            created_at=datetime.now().astimezone(pytz.timezone("Asia/Tashkent")),
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
