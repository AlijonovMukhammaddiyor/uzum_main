import uuid
from datetime import datetime, timedelta

import pytz
from django.db import models

from uzum.badge.models import Badge


def get_today_pretty():
    return datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")


def get_day_before_pretty(date_pretty: str):
    """
    Returns yesterday's date_pretty.
    Args:
        date_pretty (str): date_pretty in format %Y-%m-%d
    """
    try:
        date = datetime.strptime(date_pretty, "%Y-%m-%d").date()

        yesterday = date - timedelta(days=1)

        # Format yesterday's date as a string in 'YYYY-MM-DD' format
        yesterday_str = yesterday.strftime("%Y-%m-%d")

        return yesterday_str
    except Exception as e:
        print("Error in get_day_before: ", e)
        return None


class Sku(models.Model):
    """
    Sku - is the product variation.
    I just made separate model for it, because it has different and detailed information.
    """

    sku = models.IntegerField(unique=True, primary_key=True)
    product = models.ForeignKey("product.Product", on_delete=models.DO_NOTHING, related_name="skus")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    barcode = models.CharField(max_length=255, null=True, blank=True)
    charity_profit = models.FloatField(default=0)
    discount_badge = models.ForeignKey(Badge, on_delete=models.DO_NOTHING, related_name="skus", null=True)
    payment_per_month = models.FloatField(default=0)
    vat_amount = models.FloatField(default=0)
    vat_price = models.FloatField(default=0)
    vat_rate = models.FloatField(default=0)
    video_url = models.TextField(null=True, blank=True)
    characteristics = models.TextField(null=True, blank=True)  # json.dumps(characteristics)


class SkuAnalytics(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    sku = models.ForeignKey(Sku, on_delete=models.DO_NOTHING, related_name="analytics")
    created_at = models.DateTimeField(auto_now_add=True)
    available_amount = models.IntegerField(default=0)
    orders_amount = models.IntegerField(default=0)
    purchase_price = models.FloatField(default=0)
    full_price = models.FloatField(default=None, null=True, blank=True)
    date_pretty = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        db_index=True,
        default=get_today_pretty,
    )

    def __str__(self) -> str:
        return f"{self.sku} - {self.sku.product.title}"

    # def update_orders_amount(self):
    #     """
    #     Every day update orders_amount.
    #     Retrieve the last day analytics and subtract today's available_amount from it.
    #     """
    #     try:
    #         yesterday_pretty = get_day_before_pretty(self.date_pretty)
    #         yesterday_analytics = SkuAnalytics.objects.get(sku=self.sku, date_pretty=yesterday_pretty)
    #         orders_amount = yesterday_analytics.available_amount - self.available_amount

    #         # if orders_amount is negative, you have to set it to 0
    #         if orders_amount < 0:
    #             orders_amount = 0

    #         self.orders_amount = orders_amount
    #         self.save()
    #     except Exception as e:
    #         print("Error in update_orders_amount: ", e)
    #         return None
