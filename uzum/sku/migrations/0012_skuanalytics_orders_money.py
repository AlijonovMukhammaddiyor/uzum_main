# Generated by Django 4.1.9 on 2023-10-09 05:34

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sku", "0011_skuanalytics_orders_amount"),
    ]

    operations = [
        migrations.AddField(
            model_name="skuanalytics",
            name="orders_money",
            field=models.FloatField(default=0),
        ),
    ]
