# Generated by Django 4.1.9 on 2023-07-23 07:42

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('category', '0009_category_ancestors'),
    ]

    operations = [
        migrations.AlterField(
            model_name='categoryanalytics',
            name='total_orders_amount',
            field=models.FloatField(blank=True, default=0.0, null=True),
        ),
    ]
