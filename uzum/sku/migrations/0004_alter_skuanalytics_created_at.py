# Generated by Django 4.1.9 on 2023-06-15 02:13

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("sku", "0003_alter_skuanalytics_date_pretty"),
    ]

    operations = [
        migrations.AlterField(
            model_name="skuanalytics",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True, db_index=True),
        ),
    ]
