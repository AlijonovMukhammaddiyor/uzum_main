from django.db import connection

from uzum.category.models import CategoryAnalytics
from uzum.product.models import ProductAnalytics
from uzum.shop.models import ShopAnalytics
from uzum.sku.models import SkuAnalytics


def bulk_remove_duplicate_product_analytics(date_pretty):
    # SQL Query to get the most recent ProductAnalytics for each product on given date_pretty
    sql = f"""
    SELECT DISTINCT ON (product_id)
        id
    FROM
        product_productanalytics
    WHERE
        date_pretty = '{date_pretty}'
    ORDER BY
        product_id, created_at DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        keep_ids = [row[0] for row in cursor.fetchall()]

    # Then, get all ProductAnalytics objects for given date_pretty but exclude those whose id are in keep_ids
    pa_to_delete = ProductAnalytics.objects.filter(date_pretty=date_pretty).exclude(id__in=keep_ids)

    # Count the number of entries about to be deleted
    delete_count = pa_to_delete.count()
    print(f"About to delete {delete_count} duplicate ProductAnalytics entries for {date_pretty}")

    # Execute the delete operation
    pa_to_delete.delete()
    print(f"Deleted {delete_count} duplicate ProductAnalytics entries for {date_pretty}")


def bulk_remove_duplicate_shop_analytics(date_pretty):
    # SQL Query to get the most recent ShopAnalytics for each shop on given date_pretty
    sql = f"""
    SELECT DISTINCT ON (shop_id)
        id
    FROM
        shop_shopanalytics
    WHERE
        date_pretty = '{date_pretty}'
    ORDER BY
        shop_id, created_at DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        keep_ids = [row[0] for row in cursor.fetchall()]

    # Then, get all ShopAnalytics objects for given date_pretty but exclude those whose id are in keep_ids
    sa_to_delete = ShopAnalytics.objects.filter(date_pretty=date_pretty).exclude(id__in=keep_ids)

    # Count the number of entries about to be deleted
    delete_count = sa_to_delete.count()
    print(f"About to delete {delete_count} duplicate ShopAnalytics entries for {date_pretty}")

    # Execute the delete operation
    sa_to_delete.delete()
    print(f"Deleted {delete_count} duplicate ShopAnalytics entries for {date_pretty}")


def bulk_remove_duplicate_sku_analytics(date_pretty):
    # SQL Query to get the most recent ShopAnalytics for each shop on given date_pretty
    sql = f"""
    SELECT DISTINCT ON (sku_id)
        id
    FROM
        sku_skuanalytics
    WHERE
        date_pretty = '{date_pretty}'
    ORDER BY
        sku_id, created_at DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        keep_ids = [row[0] for row in cursor.fetchall()]

    # Then, get all SkuAnalytics objects for given date_pretty but exclude those whose id are in keep_ids
    sa_to_delete = SkuAnalytics.objects.filter(date_pretty=date_pretty).exclude(id__in=keep_ids)

    # Count the number of entries about to be deleted
    delete_count = sa_to_delete.count()
    print(f"About to delete {delete_count} duplicate SkuAnalytics entries for {date_pretty}")

    # Execute the delete operation
    sa_to_delete.delete()
    print(f"Deleted {delete_count} duplicate ShopAnalytics entries for {date_pretty}")


def bulk_remove_duplicate_category_analytics(date_pretty):
    # SQL Query to get the most recent CategoryAnalytics for each category on given date_pretty
    sql = f"""
    SELECT DISTINCT ON (category_id)
        id
    FROM
        category_categoryanalytics
    WHERE
        date_pretty = '{date_pretty}'
    ORDER BY
        category_id, created_at DESC
    """

    with connection.cursor() as cursor:
        cursor.execute(sql)
        keep_ids = [row[0] for row in cursor.fetchall()]

    # Then, get all CategoryAnalytics objects for given date_pretty but exclude those whose id are in keep_ids
    ca_to_delete = CategoryAnalytics.objects.filter(date_pretty=date_pretty).exclude(id__in=keep_ids)

    # Count the number of entries about to be deleted
    delete_count = ca_to_delete.count()
    print(f"About to delete {delete_count} duplicate CategoryAnalytics entries for {date_pretty}")

    # Execute the delete operation
    ca_to_delete.delete()
    print(f"Deleted {delete_count} duplicate CategoryAnalytics entries for {date_pretty}")
