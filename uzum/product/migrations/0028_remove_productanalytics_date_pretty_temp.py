# Generated by Django 4.1.9 on 2023-10-06 09:50

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0027_productanalytics_date_pretty_temp_and_more"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="productanalytics",
            name="date_pretty_temp",
        ),
    ]
