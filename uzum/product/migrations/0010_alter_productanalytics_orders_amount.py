# Generated by Django 4.1.9 on 2023-06-26 14:23

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0009_alter_product_adult_alter_product_created_at_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productanalytics",
            name="orders_amount",
            field=models.IntegerField(db_index=True, default=0),
        ),
    ]
