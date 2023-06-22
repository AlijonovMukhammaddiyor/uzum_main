import uuid
from django.db import models

from uzum.product.models import get_today_pretty


class Review(models.Model):
    reviewId = models.IntegerField(primary_key=True)
    product = models.ForeignKey("product.Product", on_delete=models.DO_NOTHING)
    customer = models.CharField(max_length=1024)
    content = models.TextField()
    amount_dislikes = models.IntegerField(default=0)
    amount_likes = models.IntegerField(default=0)
    is_anonymous = models.BooleanField(default=False)
    characteristics = models.TextField(null=True, blank=True)
    publish_date = models.DateTimeField()
    edited = models.BooleanField(default=False)
    rating = models.FloatField(default=0.0)
    created_at = models.DateTimeField(auto_now_add=True)
    status = models.CharField(max_length=1024, null=True, blank=True)
    photos = models.TextField(null=True, blank=True)


class Reply(models.Model):
    published_at = models.DateTimeField(auto_now_add=True)
    created_at = models.DateTimeField(auto_now_add=True)
    content = models.TextField()
    edited = models.BooleanField(default=False)
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    photos = models.TextField(null=True, blank=True)
    shop = models.ForeignKey("shop.Shop", on_delete=models.DO_NOTHING)


class PopularSeaches(models.Model):
    words = models.TextField()
    requests_count = models.IntegerField(default=100)
    created_at = models.DateTimeField(auto_now_add=True)
    date_pretty = models.CharField(max_length=1024, null=True, blank=True, default=get_today_pretty)
