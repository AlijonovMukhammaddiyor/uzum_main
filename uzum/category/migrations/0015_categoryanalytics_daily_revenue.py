# Generated by Django 4.1.9 on 2023-10-10 12:31

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("category", "0014_category_ancestors_ru"),
    ]

    operations = [
        migrations.AddField(
            model_name="categoryanalytics",
            name="daily_revenue",
            field=models.FloatField(blank=True, db_index=True, default=0, null=True),
        ),
    ]
