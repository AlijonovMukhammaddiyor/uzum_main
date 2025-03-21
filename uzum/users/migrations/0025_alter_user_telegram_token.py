# Generated by Django 4.1.9 on 2023-09-05 14:01

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("users", "0024_alter_user_telegram_token"),
    ]

    operations = [
        migrations.AlterField(
            model_name="user",
            name="telegram_token",
            field=models.UUIDField(default=uuid.uuid4, null=True, unique=True),
        ),
    ]
