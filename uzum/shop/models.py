import uuid

from django.apps import apps
from django.db import connection, models

from uzum.utils.general import get_today_pretty


def get_model(app_name, model_name):
    return apps.get_model(app_name, model_name)


class Shop(models.Model):
    seller_id = models.IntegerField(primary_key=True)
    avatar = models.TextField(null=True, blank=True)
    banner = models.TextField(null=True, blank=True)
    description = models.TextField(null=True, blank=True)
    has_charity_products = models.BooleanField(default=False)
    link = models.TextField(null=True, blank=True)
    official = models.BooleanField(default=False)
    info = models.TextField(null=True, blank=True)  # json.dumps(info)
    registration_date = models.DateTimeField(null=True, blank=True)
    title = models.TextField(null=True, blank=True)
    account_id = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class ShopAnalytics(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="analytics")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    total_products = models.IntegerField(default=0)
    total_orders = models.IntegerField(default=0, db_index=True)
    total_reviews = models.IntegerField(default=0)
    average_purchase_price = models.FloatField(default=0, null=True, blank=True)
    average_order_price = models.FloatField(default=0, null=True, blank=True)
    rating = models.FloatField(default=0)
    banners = models.ManyToManyField(
        "banner.Banner",
    )
    date_pretty = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        default=get_today_pretty,
    )

    categories = models.ManyToManyField(
        "category.Category",
    )
    position = models.IntegerField(default=0, null=True, blank=True)

    def __str__(self):
        return f"{self.shop.title} - {self.total_products}"

    @staticmethod
    def update_analytics(date_pretty: str = get_today_pretty()):
        ShopAnalytics.set_total_products(date_pretty)
        ShopAnalytics.set_shop_positions(date_pretty)
        ShopAnalytics.set_average_price(date_pretty)
        ShopAnalytics.set_categories(date_pretty)

    @staticmethod
    def set_shop_positions(date_pretty: str = get_today_pretty()):
        try:
            with connection.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE shop_shopanalytics AS sa
                    SET position = sa_new.rank
                    FROM (
                        SELECT sa_inner.id, RANK() OVER (ORDER BY sa_inner.total_orders DESC) as rank
                        FROM shop_shopanalytics as sa_inner
                        WHERE sa_inner.date_pretty = %s
                    ) AS sa_new
                    WHERE sa.id = sa_new.id
                    """,
                    [date_pretty],
                )
        except Exception as e:
            print("Error in set_shop_positions: ", e)

    @staticmethod
    def set_average_price(date_pretty: str = get_today_pretty()):
        try:
            with connection.cursor() as cursor:
                # update average_price
                cursor.execute(
                    """
                    UPDATE shop_shopanalytics sa
                    SET average_purchase_price = sub.average_price
                    FROM (
                        SELECT p.shop_id, AVG(ska.purchase_price) as average_price
                        FROM sku_skuanalytics ska
                        JOIN sku_sku s ON ska.sku_id = s.sku
                        JOIN product_product p ON s.product_id = p.product_id
                        WHERE ska.date_pretty = %s
                        GROUP BY p.shop_id
                    ) sub
                    WHERE sa.shop_id = sub.shop_id AND sa.date_pretty = %s
                    """,
                    [date_pretty, date_pretty],
                )
        except Exception as e:
            print("Error in set_average_price: ", e)

    @staticmethod
    def set_total_products(date_pretty: str = get_today_pretty()):
        from django.db import connection

        try:
            with connection.cursor() as cursor:
                # update total_products
                cursor.execute(
                    """
                    UPDATE shop_shopanalytics sa
                    SET total_products = sub.product_count
                    FROM (
                        SELECT p.shop_id, COUNT(*) as product_count
                        FROM product_productanalytics pa
                        JOIN product_product p ON pa.product_id = p.product_id
                        WHERE pa.date_pretty = %s
                        GROUP BY p.shop_id
                    ) sub
                    WHERE sa.shop_id = sub.shop_id AND sa.date_pretty = %s
                    """,
                    [date_pretty, date_pretty],
                )
        except Exception as e:
            print("Error in set_total_products: ", e)

    @staticmethod
    def set_categories(date_pretty: str = get_today_pretty()):
        from django.db import connection

        try:
            with connection.cursor() as cursor:
                # Insert new associations directly
                cursor.execute(
                    """
                    INSERT INTO shop_shopanalytics_categories(shopanalytics_id, category_id)
                    SELECT sa.id AS shopanalytics_id, p.category_id
                    FROM shop_shopanalytics sa
                    JOIN product_product p ON sa.shop_id = p.shop_id
                    JOIN product_productanalytics pa ON p.product_id = pa.product_id
                    WHERE sa.date_pretty = %s AND pa.date_pretty = %s
                    GROUP BY sa.id, p.category_id
                    ON CONFLICT DO NOTHING
                    """,
                    [date_pretty, date_pretty],
                )

        except Exception as e:
            print("Error in set_categories: ", e)
