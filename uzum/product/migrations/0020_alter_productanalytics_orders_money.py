# Generated by Django 4.1.9 on 2023-08-02 12:03

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0019_latestproductanalyticsview"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productanalytics",
            name="orders_money",
            field=models.FloatField(db_index=True, default=0.0),
        ),
    ]
