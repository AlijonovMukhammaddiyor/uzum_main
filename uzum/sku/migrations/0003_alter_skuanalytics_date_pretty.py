# Generated by Django 4.1.9 on 2023-05-29 17:13

from django.db import migrations, models
import uzum.sku.models


class Migration(migrations.Migration):
    dependencies = [
        ("sku", "0002_skuanalytics_orders_amount"),
    ]

    operations = [
        migrations.AlterField(
            model_name="skuanalytics",
            name="date_pretty",
            field=models.CharField(
                blank=True, db_index=True, default=uzum.sku.models.get_today_pretty, max_length=255, null=True
            ),
        ),
    ]
