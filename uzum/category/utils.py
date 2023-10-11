import datetime
import json
import time
import traceback
from itertools import chain

import pytz
from asgiref.sync import async_to_sync
from django.db import connection, models, transaction
from django.db.models import Avg, F, Sum
from django.db.models.functions import TruncDay
from django.utils import timezone

from uzum.banner.models import Banner
from uzum.category.models import Category, CategoryAnalytics
from uzum.jobs.campaign.utils import associate_with_shop_or_product
from uzum.jobs.category.MultiEntry import \
    get_categories_with_less_than_n_products_for_russian_title
from uzum.jobs.category.utils import get_categories_tree
from uzum.jobs.constants import MAX_ID_COUNT, PAGE_SIZE
from uzum.jobs.product.fetch_ids import get_all_product_ids_from_uzum
from uzum.product.models import ProductAnalytics
from uzum.shop.models import Shop, ShopAnalytics
from uzum.sku.models import SkuAnalytics
from uzum.utils.general import get_today_pretty


def update_category_with_sales(category_sales_map: dict, date_pretty=get_today_pretty()):
    try:
        start = time.time()

        # Fetch all the relevant CategoryAnalytics objects at once
        category_ids = list(category_sales_map.keys())
        categories = CategoryAnalytics.objects.filter(category__categoryId__in=category_ids, date_pretty=date_pretty)

        # Store the CategoryAnalytics objects in a dictionary for quick access
        category_dict = {cat.category.categoryId: cat for cat in categories}

        to_update = []  # List to store the updated CategoryAnalytics objects

        for category_id, sales in category_sales_map.items():
            category = category_dict.get(category_id)
            if not category:
                continue

            descendants = [category_id]
            if category.category.descendants:
                descendants.extend(map(int, category.category.descendants.split(",")))
                descendants = list(set(descendants))

            # update total_products_with_sales
            # category.total_products_with_sales = sum(
            #     len(category_sales_map.get(c_id, {}).get("products_with_sales", [])) for c_id in descendants
            # )
            # first get all product ids in set to remove duplicates
            product_ids = set()
            for c_id in descendants:
                product_ids.update(category_sales_map.get(c_id, {}).get("products_with_sales", []))

            category.total_products_with_sales = len(product_ids)

            # update total_shops_with_sales
            # category.total_shops_with_sales = sum(
            #     len(category_sales_map.get(c_id, {}).get("shops_with_sales", [])) for c_id in descendants
            # )
            # first get all shop ids in set to remove duplicates
            shop_ids = set()
            for c_id in descendants:
                shop_ids.update(category_sales_map.get(c_id, {}).get("shops_with_sales", []))
            category.total_shops_with_sales = len(shop_ids)

            to_update.append(category)

        # Update the CategoryAnalytics objects in bulk
        CategoryAnalytics.objects.bulk_update(to_update, ["total_products_with_sales", "total_shops_with_sales"])

        print(f"Category with sales updated in {time.time() - start} seconds")
    except Exception as e:
        print("Error in update_category_with_sales: ", e)
        traceback.print_exc()
        return None


def vacuum_table(table_name):
    with connection.cursor() as cursor:
        cursor.execute(f"VACUUM (VERBOSE, ANALYZE) {table_name};")


def seconds_until_next():
    """Get the number of seconds until midnight."""
    now = timezone.make_aware(datetime.datetime.now(), timezone=pytz.timezone("Asia/Tashkent"))
    current_hour = now.hour
    # if it is after 7 am in Tashkent, then return the number of seconds until next day 7 am
    if current_hour >= 7:
        tomorrow = now + datetime.timedelta(days=1)
        midnight = tomorrow.replace(hour=7, minute=0, second=0, microsecond=0)
        return (midnight - now).seconds

    # if it is before 7 am in Tashkent, then return the number of seconds until 7 am
    else:
        midnight = now.replace(hour=7, minute=0, second=0, microsecond=0)
        return (midnight - now).seconds


def get_date_pretty(date: datetime.datetime):
    # make sure date is in Asia/Tashkent timezone
    date = date.astimezone(pytz.timezone("Asia/Tashkent"))

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

    # start_pretty = get_date_pretty(start_date)
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


def gini_coefficient(category: Category, date_pretty: str):
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
        ShopAnalytics.objects.filter(categories__in=categories, date_pretty=date_pretty)
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


def HHI(category: Category, date_pretty: str):
    """
    This function calculates Herfindahl-Hirschman Index for a category on a given date
    Args:
        category (Category): _description_
        date (datetime.datetime): _description_

    Returns:
        _type_: _description_
    """
    categories = category.get_descendants(include_self=True)
    total_orders = CategoryAnalytics.objects.get(category=category, date_pretty=date_pretty).total_orders

    shop_analytics = (
        ShopAnalytics.objects.filter(categories__in=categories, date_pretty=date_pretty)
        .distinct()
        .order_by("total_orders")
    )

    shop_market_shares = [(shop.total_orders / total_orders) ** 2 for shop in shop_analytics]

    return sum(shop_market_shares)

def add_product_russian_titles():
    try:
        tree = get_categories_tree()
        cat_totals = {}  # mapping from id to total products given in api response

        for i, category in enumerate(tree):
            cat_totals[category["category"]["id"]] = category["total"]

        print("MAX_ID_COUNT: ", MAX_ID_COUNT)
        categories_filtered = get_categories_with_less_than_n_products_for_russian_title(MAX_ID_COUNT, cat_totals)
        product_ids: list[dict] = []  # it is [{productId: int, title: str}]

        async_to_sync(get_all_product_ids_from_uzum)(
            categories_filtered,
            product_ids,
            page_size=PAGE_SIZE,
            is_ru=True,
        )

        # remove duplicate product ids
        product_ids_dict = {d["productId"]: d["title"] for d in product_ids}
        product_ids = [{"productId": k, "title": v} for k, v in product_ids_dict.items()]
        print(f"Total product ids: {len(product_ids)}")

        with transaction.atomic():
            with connection.cursor() as cursor:
                # Create mapping table
                cursor.execute(
                    """
                    DROP TABLE IF EXISTS product_id_title_mapping;
                    CREATE TABLE product_id_title_mapping (
                        product_id INT PRIMARY KEY,
                        new_title TEXT
                    );
                """
                )

                # Insert product id and new title mapping into the table using batch insert
                values = ", ".join(["(%s, %s)"] * len(product_ids))
                query = f"""
                    INSERT INTO product_id_title_mapping (product_id, new_title)
                    VALUES {values}
                """
                cursor.execute(query, sum([list(item.values()) for item in product_ids], []))

                # Update product titles based on the mapping table only if title_ru is null
                cursor.execute(
                    """
                    UPDATE product_product
                    SET title_ru = product_id_title_mapping.new_title
                    FROM product_id_title_mapping
                    WHERE product_product.product_id = product_id_title_mapping.product_id
                    """
                )

    except Exception as e:
        print("Error in add_russian_titles: ", e)
        traceback.print_exc()
        return None


def add_product_russian_characteristics():
    try:
        tree = get_categories_tree()
        cat_totals = {}  # mapping from id to total products given in api response

        for i, category in enumerate(tree):
            cat_totals[category["category"]["id"]] = category["total"]

        print("MAX_ID_COUNT: ", MAX_ID_COUNT)
        categories_filtered = get_categories_with_less_than_n_products_for_russian_title(MAX_ID_COUNT, cat_totals)
        product_ids: list[dict] = []  # it is [{productId: int, title: str}]

        async_to_sync(get_all_product_ids_from_uzum)(
            categories_filtered,
            product_ids,
            page_size=PAGE_SIZE,
            is_ru=True,
        )

        # find which products has no russian title
        # ids = Product.objects.filter(title_ru__isnull=True).values_list("product_id", flat=True)

        # remove duplicate product ids
        product_ids_dict = {d["productId"]: json.dumps(d["characteristicValues"]) for d in product_ids}
        product_ids = [{"productId": k, "characteristics": v} for k, v in product_ids_dict.items()]
        print(f"Total product ids: {len(product_ids)}")

        with transaction.atomic():
            with connection.cursor() as cursor:
                # Create mapping table
                cursor.execute(
                    """
                    DROP TABLE IF EXISTS product_id_charcateristics_mapping;
                    CREATE TABLE product_id_charcateristics_mapping (
                        product_id INT PRIMARY KEY,
                        characteristics TEXT
                    );
                """
                )

                # Insert product id and new title mapping into the table using batch insert
                values = ", ".join(["(%s, %s)"] * len(product_ids))
                query = f"""
                    INSERT INTO product_id_charcateristics_mapping (product_id, characteristics)
                    VALUES {values}
                """
                cursor.execute(query, sum([list(item.values()) for item in product_ids], []))

                # Update product titles based on the mapping table only if title_ru is null
                cursor.execute(
                    """
                    UPDATE product_product
                    SET characteristics_ru = product_id_charcateristics_mapping.characteristics
                    FROM product_id_charcateristics_mapping
                    WHERE product_product.product_id = product_id_charcateristics_mapping.product_id
                    """
                )

    except Exception as e:
        print("Error in add_russian_titles: ", e)
        traceback.print_exc()
        return None

def set_banners_for_product_analytics(date_pretty=get_today_pretty()):
    try:
        today_date_in_uz = datetime.now(tz=pytz.timezone("Asia/Tashkent")).date()
        banners_today = Banner.objects.filter(created_at__date=today_date_in_uz)

        for banner in banners_today:
            assoc = associate_with_shop_or_product(banner.link)

            if assoc is None:
                continue

            if "product_id" in assoc:
                analytics_today = ProductAnalytics.objects.filter(
                    product__product_id=assoc["product_id"], date_pretty=date_pretty
                )
                if len(analytics_today) == 0:
                    continue

                if len(analytics_today) > 1:
                    print("More than one analytics for product", assoc["product_id"], len(analytics_today))

                analytics_today = analytics_today.first()
                analytics_today.banners.add(banner)
                analytics_today.save()

            elif "shop_id" in assoc:
                shop_an = ShopAnalytics.objects.filter(
                    shop=Shop.objects.get(link=assoc["shop_id"]), date_pretty=date_pretty
                )

                if len(shop_an) == 0:
                    continue

                if len(shop_an) > 1:
                    print("More than one analytics for shop", assoc["shop_id"], len(shop_an))
                target = shop_an.order_by("-created_at").first()  # get most recently created analytics
                target.banners.add(banner)
                target.save()

    except Exception as e:
        print("Error in setting banner(s): ", e)


def update_all_category_parents():
    try:
        tree = get_categories_tree()
        cat_parents = {}  # mapping from id to parent id
        all_categories = {}
        Category.objects.all().update(parent=None)

        for i, category in enumerate(tree):
            if category["category"]["id"] != 1:
                cat_parents[category["category"]["id"]] = category["category"]["parent"]["id"]

        categories_qs = Category.objects.filter(categoryId__in=cat_parents.keys())
        parent_qs = Category.objects.filter(categoryId__in=cat_parents.values())

        # Build dictionary for quick access
        for category in chain(categories_qs, parent_qs):
            try:
                if category.categoryId not in all_categories:
                    all_categories[category.categoryId] = category
            except Exception as e:
                print("Keyerror:", e)
                traceback.print_exc()

        # Update parent of each category
        for cat_id, parent_id in cat_parents.items():
            try:
                cat = all_categories[cat_id]
                parent = all_categories[parent_id]
                cat.parent = parent
                cat.save()
            except Exception as e:
                print("Error in update_all_category_parents:", e)
                traceback.print_exc()
            # print(f"Category {cat.title} parent set to {parent.title}")
    except Exception as e:
        print("Error in update_all_category_parents:", e)
        traceback.print_exc()
