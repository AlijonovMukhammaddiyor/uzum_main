# Generated by Django 4.1.9 on 2023-06-26 13:18

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("badge", "0001_initial"),
        ("banner", "0002_initial"),
        ("campaign", "0001_initial"),
        ("product", "0008_alter_productanalytics_position_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="product",
            name="adult",
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name="product",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="product",
            name="title",
            field=models.TextField(db_index=True),
        ),
        migrations.AlterField(
            model_name="product",
            name="updated_at",
            field=models.DateTimeField(auto_now=True),
        ),
        migrations.AlterField(
            model_name="productanalytics",
            name="badges",
            field=models.ManyToManyField(related_name="products", to="badge.badge"),
        ),
        migrations.AlterField(
            model_name="productanalytics",
            name="banners",
            field=models.ManyToManyField(to="banner.banner"),
        ),
        migrations.AlterField(
            model_name="productanalytics",
            name="campaigns",
            field=models.ManyToManyField(to="campaign.campaign"),
        ),
    ]
