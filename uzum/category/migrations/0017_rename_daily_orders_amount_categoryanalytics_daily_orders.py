# Generated by Django 4.1.9 on 2023-10-10 13:55

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("category", "0016_categoryanalytics_daily_orders_amount"),
    ]

    operations = [
        migrations.RenameField(
            model_name="categoryanalytics",
            old_name="daily_orders_amount",
            new_name="daily_orders",
        ),
    ]
