# Generated by Django 4.1.9 on 2023-10-08 18:31

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0030_product_characteristics_ru"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="product",
            name="characteristics_ru",
        ),
        migrations.RemoveField(
            model_name="productanalytics",
            name="attributes",
        ),
        migrations.RemoveField(
            model_name="productanalytics",
            name="characteristics",
        ),
        migrations.RemoveField(
            model_name="productanalytics",
            name="description",
        ),
        migrations.RemoveField(
            model_name="productanalytics",
            name="photos",
        ),
        migrations.RemoveField(
            model_name="productanalytics",
            name="title",
        ),
    ]
