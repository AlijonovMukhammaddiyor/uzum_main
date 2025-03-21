# Generated by Django 4.1.9 on 2023-09-05 13:50

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0022_user_is_telegram_connected_user_telegram_token"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="telegram_token",
            field=models.UUIDField(default=uuid.uuid4, null=True),
        ),
    ]
