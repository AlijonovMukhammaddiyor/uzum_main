from datetime import datetime
import uuid
from django.db import models
import pytz


class Product(models.Model):
    product_id = models.IntegerField(unique=True, primary_key=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True, db_index=True)
    title = models.TextField()
    description = models.TextField(default=None, null=True, blank=True)
    adult = models.BooleanField(default=False, db_index=True)
    bonus_product = models.BooleanField(default=False)
    is_eco = models.BooleanField(default=False)
    is_perishable = models.BooleanField(default=False)
    volume_discount = models.IntegerField(default=None, null=True, blank=True)
    video = models.TextField(null=True, blank=True)

    shop = models.ForeignKey(
        "shop.Shop", on_delete=models.DO_NOTHING, related_name="products", db_index=True
    )

    category = models.ForeignKey(
        "category.Category",
        on_delete=models.DO_NOTHING,
        related_name="products",
        db_index=True,
    )

    attributes = models.TextField(null=True, blank=True)  # json.dumps(attributes)
    comments = models.TextField(null=True, blank=True)  # json.dumps(comments)
    photos = models.TextField(null=True, blank=True)  # json.dumps(photos)
    characteristics = models.TextField(
        null=True, blank=True
    )  # json.dumps(characteristics)

    def __str__(self) -> str:
        return f"{self.product_id} - {self.title}"


def get_today_pretty():
    return datetime.now(tz=pytz.timezone("Asia/Tashkent")).strftime("%Y-%m-%d")


class ProductAnalytics(models.Model):
    id = models.UUIDField(
        default=uuid.uuid4,
        editable=False,
        unique=True,
        primary_key=True,
    )
    product = models.ForeignKey(
        Product, on_delete=models.DO_NOTHING, related_name="analytics"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    banners = models.ManyToManyField(
        "banner.Banner",
        db_index=True
    )
    badges = models.ManyToManyField(
        "badge.Badge",
        db_index=True
    )
    reviews_amount = models.IntegerField(default=0)
    rating = models.FloatField(default=0)
    orders_amount = models.IntegerField(default=0)
    # product can have many campaigns
    campaigns = models.ManyToManyField(
        "campaign.Campaign",
        db_index=True,
    )
    date_pretty = models.CharField(
        max_length=255, null=True, blank=True, db_index=True, default=get_today_pretty
    )
