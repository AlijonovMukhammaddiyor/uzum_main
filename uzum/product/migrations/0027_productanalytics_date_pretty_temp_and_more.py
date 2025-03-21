# Generated by Django 4.1.9 on 2023-10-06 09:45

from django.db import migrations, models

import uzum.utils.general


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0026_alter_productanalytics_date_pretty"),
    ]

    operations = [
        migrations.AddField(
            model_name="productanalytics",
            name="date_pretty_temp",
            field=models.CharField(
                blank=True, db_index=True, default=uzum.utils.general.get_today_pretty, max_length=255, null=True
            ),
        ),
        migrations.AlterModelTable(
            name="productanalytics",
            table="product_productanalytics",
        ),
    ]
