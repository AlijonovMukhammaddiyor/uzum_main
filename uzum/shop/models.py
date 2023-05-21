import uuid
from django.db import models

from uzum.product.models import get_today_pretty


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
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.title


class ShopAnalytics(models.Model):
    id = models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True)
    shop = models.ForeignKey(Shop, on_delete=models.CASCADE, related_name="analytics")
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    total_products = models.IntegerField(default=0)
    total_orders = models.IntegerField(default=0)
    total_reviews = models.IntegerField(default=0)
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

    def __str__(self):
        return f"{self.shop.title} - {self.total_products}"
