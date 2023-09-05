# Generated by Django 4.1.9 on 2023-09-05 13:42

from django.db import migrations, models
import uuid


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0021_user_favourite_products_user_favourite_shops"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="is_telegram_connected",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="telegram_token",
            field=models.UUIDField(default=uuid.uuid4),
        ),
    ]
