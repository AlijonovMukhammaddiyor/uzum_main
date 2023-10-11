# Generated by Django 4.1.9 on 2023-05-17 13:19

import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("product", "0001_initial"),
        ("shop", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Review",
            fields=[
                ("reviewId", models.IntegerField(primary_key=True, serialize=False)),
                ("customer", models.CharField(max_length=1024)),
                ("content", models.TextField()),
                ("amount_dislikes", models.IntegerField(default=0)),
                ("amount_likes", models.IntegerField(default=0)),
                ("is_anonymous", models.BooleanField(default=False)),
                ("characteristics", models.TextField(blank=True, null=True)),
                ("publish_date", models.DateTimeField()),
                ("edited", models.BooleanField(default=False)),
                ("rating", models.FloatField(default=0.0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("status", models.CharField(blank=True, max_length=1024, null=True)),
                ("photos", models.TextField(blank=True, null=True)),
                ("product", models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to="product.product")),
            ],
        ),
        migrations.CreateModel(
            name="Reply",
            fields=[
                ("published_at", models.DateTimeField(auto_now_add=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("content", models.TextField()),
                ("edited", models.BooleanField(default=False)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("photos", models.TextField(blank=True, null=True)),
                ("shop", models.ForeignKey(on_delete=django.db.models.deletion.DO_NOTHING, to="shop.shop")),
            ],
        ),
    ]
