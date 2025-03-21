# Generated by Django 4.1.9 on 2023-05-17 13:19

import uuid

import django.db.models.deletion
from django.db import migrations, models

from uzum.utils.general import get_today_pretty


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("category", "0001_initial"),
        ("badge", "0001_initial"),
        ("campaign", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Product",
            fields=[
                ("product_id", models.IntegerField(primary_key=True, serialize=False, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True, db_index=True)),
                ("title", models.TextField()),
                ("description", models.TextField(blank=True, default=None, null=True)),
                ("adult", models.BooleanField(db_index=True, default=False)),
                ("bonus_product", models.BooleanField(default=False)),
                ("is_eco", models.BooleanField(default=False)),
                ("is_perishable", models.BooleanField(default=False)),
                ("volume_discount", models.IntegerField(blank=True, default=None, null=True)),
                ("video", models.TextField(blank=True, null=True)),
                ("attributes", models.TextField(blank=True, null=True)),
                ("comments", models.TextField(blank=True, null=True)),
                ("photos", models.TextField(blank=True, null=True)),
                ("characteristics", models.TextField(blank=True, null=True)),
                ("badges", models.ManyToManyField(db_index=True, related_name="products", to="badge.badge")),
                (
                    "category",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING, related_name="products", to="category.category"
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="ProductAnalytics",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False, unique=True
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("reviews_amount", models.IntegerField(default=0)),
                ("rating", models.FloatField(default=0)),
                ("orders_amount", models.IntegerField(default=0)),
                (
                    "date_pretty",
                    models.CharField(
                        blank=True,
                        db_index=True,
                        default=get_today_pretty,
                        max_length=255,
                        null=True,
                    ),
                ),
                ("campaigns", models.ManyToManyField(db_index=True, to="campaign.campaign")),
                (
                    "product",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.DO_NOTHING, related_name="analytics", to="product.product"
                    ),
                ),
            ],
        ),
    ]
