# Generated by Django 4.1.9 on 2023-05-24 14:28

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("category", "0002_categoryanalytics_date_pretty"),
    ]

    operations = [
        migrations.AddField(
            model_name="category",
            name="descendants",
            field=models.TextField(blank=True, null=True),
        ),
    ]
