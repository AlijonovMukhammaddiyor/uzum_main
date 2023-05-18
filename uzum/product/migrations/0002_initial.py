# Generated by Django 4.1.9 on 2023-05-17 13:19

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("review", "0001_initial"),
        ("product", "0001_initial"),
        ("shop", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="reviews",
            field=models.ManyToManyField(related_name="products", to="review.review"),
        ),
        migrations.AddField(
            model_name="product",
            name="shop",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.DO_NOTHING, related_name="products", to="shop.shop"
            ),
        ),
    ]
