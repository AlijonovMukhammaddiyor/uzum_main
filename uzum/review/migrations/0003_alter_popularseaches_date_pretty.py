# Generated by Django 4.1.9 on 2023-06-22 00:28

from django.db import migrations, models
import uzum.product.models


class Migration(migrations.Migration):
    dependencies = [
        ("review", "0002_popularseaches"),
    ]

    operations = [
        migrations.AlterField(
            model_name="popularseaches",
            name="date_pretty",
            field=models.CharField(
                blank=True, default=uzum.product.models.get_today_pretty, max_length=1024, null=True
            ),
        ),
    ]
