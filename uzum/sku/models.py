import uuid

from django.db import models

from uzum.badge.models import Badge
from uzum.utils.general import get_today_pretty


class Sku(models.Model):
    """
    Sku - is the product variation.
    I just made separate model for it, because it has different and detailed information.
    """

    sku = models.IntegerField(unique=True, primary_key=True)
    product = models.ForeignKey("product.Product", on_delete=models.DO_NOTHING, related_name="skus", db_index=True)
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
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    available_amount = models.IntegerField(default=0)
    orders_amount = models.IntegerField(default=0)
    purchase_price = models.FloatField(default=0, db_index=True)
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
