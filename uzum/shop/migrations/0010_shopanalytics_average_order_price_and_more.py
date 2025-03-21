# Generated by Django 4.1.9 on 2023-07-05 20:43

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("shop", "0009_remove_shopanalytics_daily_position_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="shopanalytics",
            name="average_order_price",
            field=models.FloatField(default=0),
        ),
        migrations.AddField(
            model_name="shopanalytics",
            name="average_purchase_price",
            field=models.FloatField(default=0),
        ),
    ]
