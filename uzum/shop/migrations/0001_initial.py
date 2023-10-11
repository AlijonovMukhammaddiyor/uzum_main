# Generated by Django 4.1.9 on 2023-05-17 13:19

import uuid

import django.db.models.deletion
from django.db import migrations, models

from uzum.utils.general import get_today_pretty


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Shop",
            fields=[
                ("seller_id", models.IntegerField(primary_key=True, serialize=False)),
                ("avatar", models.TextField(blank=True, null=True)),
                ("banner", models.TextField(blank=True, null=True)),
                ("description", models.TextField(blank=True, null=True)),
                ("has_charity_products", models.BooleanField(default=False)),
                ("link", models.TextField(blank=True, null=True)),
                ("official", models.BooleanField(default=False)),
                ("info", models.TextField(blank=True, null=True)),
                ("registration_date", models.DateTimeField(blank=True, null=True)),
                ("title", models.TextField(blank=True, null=True)),
                ("account_id", models.IntegerField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="ShopAnalytics",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("total_products", models.IntegerField(default=0)),
                ("total_orders", models.IntegerField(default=0)),
                ("total_reviews", models.IntegerField(default=0)),
                ("rating", models.FloatField(default=0)),
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
                (
                    "shop",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE, related_name="analytics", to="shop.shop"
                    ),
                ),
            ],
        ),
    ]
