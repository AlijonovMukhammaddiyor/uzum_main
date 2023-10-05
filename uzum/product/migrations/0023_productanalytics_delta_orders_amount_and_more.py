# Generated by Django 4.1.9 on 2023-10-05 05:51

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0022_productanalytics_attributes_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="productanalytics",
            name="delta_orders_amount",
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
        migrations.AddField(
            model_name="productanalytics",
            name="real_orders_money",
            field=models.FloatField(db_index=True, default=0.0),
        ),
    ]
