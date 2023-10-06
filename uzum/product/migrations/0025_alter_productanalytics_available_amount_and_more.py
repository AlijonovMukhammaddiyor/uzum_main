# Generated by Django 4.1.9 on 2023-10-06 09:26

from django.db import migrations, models
import uzum.utils.general


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0024_rename_delta_orders_amount_productanalytics_real_orders_amount"),
    ]

    operations = [
        migrations.AlterField(
            model_name="productanalytics",
            name="available_amount",
            field=models.IntegerField(db_index=True, default=0),
        ),
        migrations.AlterField(
            model_name="productanalytics",
            name="date_pretty",
            field=models.CharField(blank=True, default=uzum.utils.general.get_today_pretty, max_length=255, null=True),
        ),
        migrations.AlterField(
            model_name="productanalytics",
            name="real_orders_amount",
            field=models.IntegerField(blank=True, db_index=True, default=0, null=True),
        ),
        migrations.AlterField(
            model_name="productanalytics",
            name="real_orders_money",
            field=models.FloatField(default=0.0),
        ),
    ]
