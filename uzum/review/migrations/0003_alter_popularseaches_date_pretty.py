# Generated by Django 4.1.9 on 2023-06-22 00:28

from django.db import migrations, models

from uzum.utils.general import get_today_pretty


class Migration(migrations.Migration):
    dependencies = [
        ("review", "0002_popularseaches"),
    ]

    operations = [
        migrations.AlterField(
            model_name="popularseaches",
            name="date_pretty",
            field=models.CharField(blank=True, default=get_today_pretty, max_length=1024, null=True),
        ),
    ]
