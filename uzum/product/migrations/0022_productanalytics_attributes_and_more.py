# Generated by Django 4.1.9 on 2023-09-30 13:15

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0021_productanalytics_score"),
    ]

    operations = [
        migrations.AddField(
            model_name="productanalytics",
            name="attributes",
            field=models.TextField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="productanalytics",
            name="characteristics",
            field=models.TextField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="productanalytics",
            name="description",
            field=models.TextField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="productanalytics",
            name="photos",
            field=models.TextField(blank=True, default=None, null=True),
        ),
        migrations.AddField(
            model_name="productanalytics",
            name="title",
            field=models.TextField(blank=True, default=None, null=True),
        ),
    ]
